const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.filename=name;m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const hit=find(child,predicate);if(hit)return hit;}}
const lib=load('src/lib/review-workspace.ts'),tick=()=>new Promise(resolve=>setImmediate(resolve));
test('one main action starts AI grading; polling shows its criterion score without overwriting teacher edits or publishing',async()=>{
 const slots=[],effects=[],calls=[];let cursor=0,tree,phase='idle',poll;
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});},useCallback:(fn,deps)=>{const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps))slots[i]={deps,value:fn};return slots[i].value;},useEffect:(fn,deps)=>{const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps)){slots[i]={deps};effects.push(fn);}}};
 const data={submission_id:'s',assignment_id:'a',title:'Midterm',student_name:'Ada',file_name:'Answer.pdf',file_type:'pdf',maximum_score:25,questions:[{id:'q',title:'Midterm',criteria:[{criterion_id:'c',description:'1 задача',maximum_points:25}]}],structure:{pages:[{number:1,text:'A solution'}],warnings:[]},reviews:[],published_grade:null};
 const version={id:'v',job_id:'job',rubric:{id:'rubric',spec:{category:'lab_report',instructions:'Solve the task.',criteria:[{question_id:'q',criterion_id:'c',description:'1 задача',maximum_points:25}]}},result:{criteria:[{question_id:'q',criterion_id:'c',proposed_score:17.5,rationale:'A partial solution.',finding:'mixed'}]},decisions:[],source:{sections:[]}};
 const previousWindow=global.window,previousDocument=global.document;
 global.window={location:{search:''},addEventListener(){},removeEventListener(){},setInterval(fn){poll=fn;return 1;},clearInterval(){}};global.document={addEventListener(){},removeEventListener(){}};
 const Null=()=>null,Panel=()=>null;
 const {TeacherReviewWorkspace}=load('src/components/review/teacher-review-workspace.tsx',{react:hooks,'next/navigation':{useRouter:()=>({})},'../../lib/review-workspace':lib,'../../lib/platform':{platformRequest:async(url,body)=>{calls.push([url,body]);if(body){assert.equal(url,'/api/assessment/s');assert.deepEqual(body,{prepare:true,reanalyze:false});phase='active';return{id:'job',status:'awaiting_source'};}if(url.includes('/assessment/'))return{items:phase==='done'?[version]:[],jobs:phase==='idle'?[]:[{id:'job',status:phase==='done'?'needs_review':'awaiting_source',error:''}],supported:true};return data;}},'../assessment-panel':{RubricReviewPanel:Panel},'./document-viewer':{DocumentViewer:Null},'./submission-overview':{SubmissionOverview:Null},'./review-action-bar':{ReviewActionBar:Null},'./decision-memory':{DecisionMemory:Null},'./question-review-tools':{QuestionPages:Null,QuestionReviewNavigation:Null},'./assessment-diagnostics':{AssessmentDiagnostics:Null},'./review-tools':{ReviewToolsMenu:Null}});
 const view=()=>{cursor=0;tree=TeacherReviewWorkspace({submissionId:'s'});for(const effect of effects.splice(0))effect();};
 try{
  view();await tick();view();assert.equal(calls.filter(c=>c[1]).length,0);
  const start=find(tree,n=>n.type==='button'&&n.props.children==='Оценить по критериям');assert.ok(start);start.props.onClick();start.props.onClick();await tick();view();
  assert.equal(calls.filter(c=>c[1]).length,1);assert.ok(poll);
  find(tree,n=>n.type===Panel).props.onChange(lib.criterionKey('q','c'),{points:'19'});view();
  phase='done';poll();await tick();view();
  const panel=find(tree,n=>n.type===Panel);
  assert.equal(panel.props.criteria[0].suggestion.proposed_score,17.5);
  assert.equal(panel.props.editor.criteria[lib.criterionKey('q','c')].points,'19');assert.equal(panel.props.editor.mode,'manual');
  assert.equal(calls.filter(c=>c[1]).length,1);assert.equal(data.published_grade,null);
 }finally{global.window=previousWindow;global.document=previousDocument;}
});
