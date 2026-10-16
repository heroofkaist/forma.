const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
const lib=load('src/lib/assignment-workspace.ts'),status=load('src/lib/submission-status.ts'),link={default:({children,...props})=>React.createElement('a',props,children)};
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const c of React.Children.toArray(node.props.children)){const hit=find(c,predicate);if(hit)return hit;}}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const work={id:'older',student_id:'student-1',student_name:'Ada',file_name:'Original.pdf',file_type:'pdf',submitted_at:'2026-10-16T01:00:00Z',review_status:'published',review_points:0,review_maximum:10,has_draft:false,processing_status:'failed',similarity:{analysis_status:'completed',match_ratio:0,candidate_count:1}};
const data={id:'assignment',students:[{student_id:'student-1',student_name:'Ada',active:true},{student_id:'student-2',student_name:'Ivan',active:true}],items:[work,{...work,id:'latest',file_name:'Revision.pdf',submitted_at:'2026-10-16T02:00:00Z',review_status:'unreviewed',review_points:null,similarity:{analysis_status:'missing',match_ratio:null}}]};
test('assignment roster groups immutable attempts without hiding students who have not submitted',()=>{
 const rows=lib.studentWorks(data);assert.equal(rows.length,2);assert.equal(rows[0].latest.id,'latest');assert.equal(rows[0].attempts[1].review_points,0);assert.equal(rows[1].latest,null);
 assert.equal(lib.filterStudentWorks(rows,'student-2','all')[0].student_name,'Ivan');assert.equal(lib.filterStudentWorks(rows,'original.pdf','all')[0].student_name,'Ada');assert.equal(lib.filterStudentWorks(rows,'','missing').length,1);assert.equal(lib.filterStudentWorks(rows,'','unreviewed').length,1);assert.equal(lib.filterStudentWorks(rows,'','reviewed').length,0);
 for(const state of ['missing','failed','no_sources','insufficient_text','incomplete'])assert.notEqual(lib.textSimilarityLabel({analysis_status:state,match_ratio:0}),'0%');
 assert.equal(lib.textSimilarityLabel(work.similarity),'0%');assert.equal(lib.signalScore({status:'completed',score:NaN}),null);assert.equal(lib.signalScore({status:'insufficient',score:0}),null);assert.equal(lib.signalScore({status:'completed',score:0}),0);
});
test('assignment register renders identity, original, prior published zero and explicit missing report with working filters',()=>{
 const slots=[];let cursor,tree;
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=v;}];}};
 const {AssignmentRegister}=load('src/components/assignment/assignment-workspace.tsx',{react:hooks,'next/link':link,'../assignment-template':{},'../assignment-briefs':{},'./integrity-signal':{IntegritySignal:()=>null},'../../lib/document-integrity':{},'./comparison-panel':{},'../../lib/api':{},'../../lib/platform':{},'../../lib/submission-status':status,'../../lib/assignment-workspace':lib});
 const view=()=>render(React.createElement(()=>{cursor=0;tree=AssignmentRegister({data});return tree;}));
 let html=view();for(const text of ['student-1','student-2','Revision.pdf','Работа не отправлена','Не сравнивалось','Опубликована студенту · 0 / 10'])assert.ok(html.includes(text),text);
 assert.match(html,/review\?panel=assessment/);assert.match(html,/review\?panel=document/);assert.match(html,/originality/);
 find(tree,n=>n.type==='select').props.onChange({target:{value:'missing'}});html=view();assert.match(html,/Ivan/);assert.doesNotMatch(html,/Revision.pdf/);
 find(tree,n=>n.type==='input').props.onChange({target:{value:'not present'}});assert.match(view(),/По выбранным фильтрам студентов нет/);
});
test('local comparison loads saved results without POST, serializes run clicks and retains context on failure',async()=>{
 const slots=[];let cursor,tree,start,finish;const calls=[];
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});},useEffect:fn=>{start??=fn;}};
 const {ComparisonPanel}=load('src/components/assignment/comparison-panel.tsx',{react:hooks,'next/link':link,'./comparison-report':{ComparisonReport:()=>null},'../../lib/assignment-workspace':lib,'../../lib/platform':{platformRequest:async(...args)=>{calls.push(args);if(args.length===1)return{status:'missing',documents:[],pairs:[],stale:false};return await new Promise((resolve,reject)=>{finish={resolve,reject};});}}});
 const props={assignmentId:'a',students:[{student_id:'1',student_name:'Ada',latest:work},{student_id:'2',student_name:'Ivan',latest:{...work,id:'2'}}],revision:'one'};
 const view=()=>render(React.createElement(()=>{cursor=0;tree=ComparisonPanel(props);return tree;}));
 view();assert.equal(calls.length,0);start();await tick();assert.match(view(),/Новый анализ ещё не запускался/);assert.equal(calls.length,1);
 find(tree,n=>n.type==='textarea').props.onChange({target:{value:'Allowed common template'}});view();const run=find(tree,n=>n.type==='button');run.props.onClick();run.props.onClick();assert.equal(calls.length,2);assert.deepEqual(calls[1][1],{context:'Allowed common template'});
 finish.reject(Error('Synthetic timeout'));await tick();assert.match(view(),/Synthetic timeout/);assert.equal(find(tree,n=>n.type==='textarea').props.value,'Allowed common template');
});
test('older API responses without a roster still show submitted work',()=>{
 const rows=lib.studentWorks({items:[work]});assert.equal(rows.length,1);assert.equal(rows[0].student_id,work.student_id);assert.equal(rows[0].latest.id,work.id);
 assert.deepEqual(lib.studentWorks({items:[]}),[]);
});
