const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.filename=name;m.paths=Module._nodeModulePaths(path.dirname(name));const original=m.require.bind(m);m.require=key=>imports[key]??original(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const result=find(child,predicate);if(result)return result;}}
function harness(file,imports){const slots=[];let cursor,tree,start;const hooks={...React,useEffect:effect=>{start??=effect;},useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=typeof init==='function'?init():init;return[slots[i],v=>slots[i]=typeof v==='function'?v(slots[i]):v];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});}};const {default:Page}=load(file,{...imports,react:hooks});return{view(){return render(React.createElement(()=>{cursor=0;tree=Page();return tree;}));},get tree(){return tree;},start(){start();}};}
const tick=()=>new Promise(r=>setImmediate(r)),link={default:({children,...props})=>React.createElement('a',props,children)},shell={AppShell:({children})=>React.createElement('main',null,children)};
test('creating a course offering rejects duplicate submissions and preserves the entered group after a recoverable error',async()=>{
 let calls=0,reject;
 const ui=harness('src/app/teacher/page.tsx',{'next/link':link,'../../components/app-shell':shell,'../../components/auth-provider':{useAuth:()=>({enabled:true,user:{account_id:'test'}})},'../../lib/platform':{platformRequest:async()=>({review_queue:[]})},'../../lib/academic':{academicApi:{offerings:async()=>[],courses:async()=>[{id:'course',code:'PHYS',name:'Physics'}],createOffering:async()=>{calls++;return new Promise((_,r)=>reject=r);}}}});
 ui.view();ui.start();await tick();ui.view();find(ui.tree,n=>n.type==='button'&&n.props['aria-controls']==='new-offering-form').props.onClick();ui.view();
 const inputs=[];function collect(n){if(!React.isValidElement(n))return;if(n.type==='input')inputs.push(n);React.Children.forEach(n.props.children,collect);}collect(ui.tree);inputs.find(n=>n.props.value==='01').props.onChange({target:{value:'02B'}});ui.view();
 const form=find(ui.tree,n=>n.type==='form');form.props.onSubmit({preventDefault(){}});form.props.onSubmit({preventDefault(){}});assert.equal(calls,1);assert.match(ui.view(),/Создаём поток/);
 reject(Error('Temporary outage'));await tick();let html=ui.view();assert.match(html,/Temporary outage/);assert.match(html,/value="02B"/);assert.doesNotMatch(html,/Создаём поток/);
 find(ui.tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});assert.equal(calls,2);reject(Error('Retry failed'));await tick();
});
test('review queue recovers from a request failure, filters loaded work, and resets an empty search',async()=>{
 let fail=true;const item={id:'work',student_name:'Анна Ким',assignment_title:'Законы Ньютона',submitted_at:'invalid'};
 const ui=harness('src/app/teacher/review/page.tsx',{'next/link':link,'../../../components/app-shell':shell,'../../../lib/platform':{platformRequest:async()=>{if(fail)throw Error('Queue unavailable');return{review_queue:[item]};}}});
 ui.view();ui.start();await tick();assert.match(ui.view(),/Queue unavailable/);fail=false;find(ui.tree,n=>n.type==='button'&&n.props.children==='Повторить загрузку').props.onClick();await tick();let html=ui.view();assert.match(html,/Анна Ким/);assert.match(html,/Дата не указана/);assert.doesNotMatch(html,/Invalid Date/);
 find(ui.tree,n=>n.type==='input').props.onChange({target:{value:'нет такого студента'}});assert.match(ui.view(),/Работы не найдены/);find(ui.tree,n=>n.type==='button'&&n.props.children==='Сбросить поиск').props.onClick();assert.match(ui.view(),/Законы Ньютона/);
});
test('review overview tolerates invalid dates and keeps published zero distinct from unavailable scores',()=>{
 const {SubmissionOverview}=load('src/components/review/submission-overview.tsx',{'next/link':link});
 const data={assignment_id:'a',title:'Physics',student_name:'Анна',file_name:'answer.pdf',submitted_at:'invalid',maximum_score:20,published_grade:{points:0,maximum_score:20}};
 const html=render(React.createElement(SubmissionOverview,{data}));assert.match(html,/0 \/ 20/);assert.doesNotMatch(html,/Invalid Date|NaN|undefined/);
});
