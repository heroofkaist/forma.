const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const filename=path.resolve(file),m=new Module(filename,module);m.filename=filename;m.paths=Module._nodeModulePaths(path.dirname(filename));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,filename);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const hit=find(child,predicate);if(hit)return hit;}}
function harness(){let cursor=0;const state=[],effects=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);return{hooks:{...React,useState:init=>{const i=cursor++;if(!(i in state))state[i]=typeof init==='function'?init():init;return[state[i],value=>state[i]=typeof value==='function'?value(state[i]):value];},useRef:init=>{const i=cursor++;return state[i]??(state[i]={current:init});},useEffect:(fn,deps)=>{const i=cursor++;if(!same(state[i],deps)){state[i]=deps;effects.push(fn);}}},view(fn){cursor=0;const result=fn();for(const effect of effects.splice(0))effect();return result;}};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('score formatting rejects invalid values, preserves a real zero and hides generated placeholders only',()=>{
 const {scoreLabel,aiText,dateLabel}=require('../src/lib/teacher-display.ts');
 assert.equal(scoreLabel(0,5),'0');assert.equal(scoreLabel(0.1+0.2,5),'0,3');
 for(const n of [null,undefined,NaN,Infinity,-1,6,'3'])assert.equal(scoreLabel(n,5),'—');
 for(const text of ['undefined','[object Object]','NaN','null','{"score":4}'])assert.equal(aiText(text,'Нужно проверить'),'Нужно проверить');
 assert.equal(aiText('Проверьте $x=0$.'),'Проверьте $x=0$.');assert.equal(dateLabel('invalid'),'Дата не указана');
});

test('attention filter distinguishes an unavailable score from a teacher-confirmed zero',()=>{
 const {studentWorks,filterStudentWorks}=require('../src/lib/assignment-workspace.ts');
 const rows=studentWorks({students:[{student_id:'a',student_name:'A'},{student_id:'b',student_name:'B'}],items:[{id:'s1',student_id:'a',file_name:'one.pdf',submitted_at:'2026-10-17',review_status:'unreviewed',attention:{kind:'evidence'}},{id:'s2',student_id:'b',file_name:'two.pdf',submitted_at:'2026-10-17',review_status:'confirmed',review_points:0,attention:{kind:'reviewed'}}]});
 assert.deepEqual(filterStudentWorks(rows,'','attention').map(r=>r.student_id),['a']);assert.deepEqual(filterStudentWorks(rows,'','reviewed').map(r=>r.student_id),['b']);
});

test('teacher guide saves explicit rules once, preserves the example selection and performs no inference',async()=>{
 const h=harness(),calls=[],win=global.window,doc=global.document;global.document={addEventListener(){},removeEventListener(){}};global.window={addEventListener(){},removeEventListener(){}};
 const guide={id:null,stale:false,content:{rules:[],reference_review_ids:[],feedback_focus:''},questions:[{id:'q',title:'Question',statement:'Explain the method.',criteria:[{criterion_id:'c',description:'Method and calculation',maximum_points:5}]}],examples:[{review_id:'review',submission_id:'source',file_name:'checked.pdf',criteria:[{question_id:'q',criterion_id:'c',points:3,ai_score:0}]}]};
 const {TeachingGuide}=load('src/components/assignment/teaching-guide.tsx',{react:h.hooks,'../../lib/platform':{platformRequest:async(url,body)=>{calls.push([url,body]);return body?{id:'saved',content:{rules:body.rules,reference_review_ids:body.reference_review_ids,feedback_focus:body.feedback_focus}}:guide;}}});
 const props={assignmentId:'a'};let tree;const view=()=>tree=h.view(()=>TeachingGuide(props));
 try{view();await tick();view();assert.equal(calls.length,1);find(tree,n=>n.type==='textarea'&&n.props.maxLength===500).props.onChange({target:{value:'A correct method with an arithmetic error earns 3 out of 5.'}});view();find(tree,n=>n.type==='input'&&n.props.type==='checkbox').props.onChange({target:{checked:true}});view();const save=find(tree,n=>n.type==='button'&&n.props.children==='Сохранить правила');save.props.onClick();save.props.onClick();await tick();view();assert.equal(calls.filter(c=>c[1]).length,1);assert.equal(calls[1][0],'/api/teaching/assignments/a/guide');assert.equal(calls[1][1].expected_id,null);assert.deepEqual(calls[1][1].reference_review_ids,['review']);assert.equal(calls[1][1].rules[0].criterion_id,'c');assert.ok(!calls.some(c=>c[0].includes('/assessment/')));assert.match(render(tree),/Правила сохранены для новых проверок/);}finally{global.window=win;global.document=doc;}
});

test('comment bank inserts the selected explanation without adopting its historical score',async()=>{
 const h=harness(),changes=[];
 const {SavedComments}=load('src/components/review/saved-comments.tsx',{react:h.hooks,'../../lib/platform':{platformRequest:async()=>({items:[{id:'card',title:'Units',feedback:'Explain units in your final step.',points:5}]})}});
 const props={submissionId:'s',questionId:'q',criterionId:'c',value:'Existing feedback.',onChange:text=>changes.push(text),disabled:false};let tree;const view=()=>tree=h.view(()=>SavedComments(props));
 view();find(tree,n=>n.type==='button').props.onClick();await tick();view();find(tree,n=>n.type==='button'&&n.props.children==='Вставить текст').props.onClick();assert.deepEqual(changes,['Existing feedback.\n\nExplain units in your final step.']);
});

test('citation control opens the validated citation rather than just changing the page',()=>{
 const {EvidenceLink}=require('../src/components/review/criterion-card.tsx');let opened=0,pages=0;
 const tree=EvidenceLink({evidence:{page_number:2,quote:'Original'},onPage:()=>pages++,onEvidence:()=>opened++});tree.props.onClick();assert.equal(opened,1);assert.equal(pages,0);
});
