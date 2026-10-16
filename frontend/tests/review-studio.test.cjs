const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const c of React.Children.toArray(node.props.children)){const hit=find(c,predicate);if(hit)return hit;}}
const lib=load('src/lib/review-workspace.ts'),tick=()=>new Promise(resolve=>setImmediate(resolve));
const data={submission_id:'s',assignment_id:'a',title:'Synthetic task',student_name:'Synthetic student',file_name:'Synthetic.pdf',file_type:'pdf',maximum_score:10,questions:[{id:'q',title:'Question',statement:'Explain your method.',criteria:[{criterion_id:'c',description:'Method',maximum_points:10}]}],structure:{pages:[{number:1,text:'Synthetic text'}],warnings:[]},reviews:[],published_grade:null};
test('grading fields are visible immediately without expanding a criterion or exposing tool controls',()=>{
 const {RubricCriterionCard}=load('src/components/review/criterion-card.tsx',{'../../lib/review-workspace':lib});
 const html=render(React.createElement(RubricCriterionCard,{criterion:lib.reviewCriteria(data)[0],index:0,value:{points:'',feedback:'',action:'unreviewed'},manual:true,busy:false,dirty:false,savedState:'unreviewed'}));
 assert.match(html,/>Ваш балл<\/label>/);assert.match(html,/type="number"/);assert.match(html,/<textarea/);assert.doesNotMatch(html,/<details|<summary|aria-expanded|Нет предложения|Сохранённых предложений/);
});
test('action bar provides one next action and keeps saving separate from publishing',()=>{
 const {ReviewActionBar}=load('src/components/review/review-action-bar.tsx',{'../../lib/review-workspace':lib});
 let save=0,publish=0;const props={dirty:true,busy:false,hasSaved:false,total:0,maximum:10,error:null,onSave(){},onConfirm(){save++;},onPublish(){publish++;},publishable:false,savedState:'unreviewed'};
 let tree=ReviewActionBar(props);let main=find(tree,n=>n.type==='button'&&n.props.className.includes('rw-primary'));
 assert.equal(main.props.disabled,false);main.props.onClick();assert.equal(save,1);assert.equal(publish,0);
 tree=ReviewActionBar({...props,dirty:false,hasSaved:true,publishable:true,savedState:'confirmed'});main=find(tree,n=>n.type==='button'&&n.props.className.includes('rw-primary'));main.props.onClick();assert.equal(save,1);assert.equal(publish,1);
 assert.match(render(tree),/Опубликовать оценку/);assert.equal(React.Children.count(find(tree,n=>n.props.className==='rw-review-actions').props.children),2);
 assert.equal(find(ReviewActionBar({...props,total:null}),n=>n.type==='button'&&n.props.className.includes('rw-primary')).props.disabled,true);
});
test('tabs keep an entered zero; saving serializes clicks and publication requires an explicit dialog',async()=>{
 const slots=[],effects=[];let cursor,tree;const calls=[];let saved=false;
 const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});},useCallback:(fn,deps)=>{const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps))slots[i]={deps,value:fn};return slots[i].value;},useEffect:(fn,deps)=>{const i=cursor++;if(!slots[i]||!same(slots[i].deps,deps)){slots[i]={deps};effects.push(fn);}}};
 const previousWindow=global.window,previousDocument=global.document;
 global.window={location:{search:''},addEventListener(){},removeEventListener(){},setInterval(){return 1;},clearInterval(){}};global.document={addEventListener(){},removeEventListener(){}};
 const Null=()=>null,Card=()=>null,Action=()=>null;
 const {TeacherReviewWorkspace}=load('src/components/review/teacher-review-workspace.tsx',{react:hooks,'next/navigation':{useRouter:()=>({push(){}})},'../../lib/review-workspace':lib,'../../lib/platform':{platformRequest:async(url,body)=>{calls.push([url,body]);if(body&&url.endsWith('/publish'))return{};if(body){saved=true;assert.equal(body.draft,false);assert.equal(body.criteria[0].points,0);return{};}return url.includes('/assessment/')?{items:[],jobs:[],supported:true}:{...data,reviews:saved?[{id:'r',created_at:'2026-10-16',criteria:[{question_id:'q',criterion_id:'c',points:0,confirmed:true}],feedback:''}]:[]};}},'../assessment-panel':{RubricReviewPanel:Card},'./document-viewer':{DocumentViewer:Null},'./submission-overview':{SubmissionOverview:Null},'./review-action-bar':{ReviewActionBar:Action},'./decision-memory':{DecisionMemory:Null},'./question-review-tools':{QuestionPages:Null,QuestionReviewNavigation:Null},'./assessment-diagnostics':{AssessmentDiagnostics:Null},'./review-tools':{ReviewToolsMenu:Null}});
 const view=()=>{cursor=0;tree=TeacherReviewWorkspace({submissionId:'s'});return tree;};
 try {
  view();for(const fn of effects.splice(0))fn();await tick();view();assert.equal(calls.filter(c=>c[1]).length,0);
  find(tree,n=>n.type===Card).props.onChange(lib.criterionKey('q','c'),{points:'0'});view();
  find(tree,n=>n.props.id==='review-tab-assignment').props.onClick();view();assert.equal(find(tree,n=>n.props.id==='review-view-grade').props.hidden,true);
  find(tree,n=>n.props.id==='review-tab-grade').props.onClick();view();assert.equal(find(tree,n=>n.type===Card).props.editor.criteria[lib.criterionKey('q','c')].points,'0');
  let action=find(tree,n=>n.type===Action);action.props.onConfirm();action.props.onConfirm();await tick();view();assert.equal(calls.filter(c=>c[1]).length,1);assert.equal(find(tree,n=>n.type===Action).props.publishable,true);
  find(tree,n=>n.type===Action).props.onPublish();view();assert.equal(calls.filter(c=>c[0].endsWith('/publish')).length,0);
  const dialog=find(tree,n=>n.props.confirmLabel==='Опубликовать для студента');assert.ok(dialog);dialog.props.onConfirm();await tick();assert.equal(calls.filter(c=>c[0].endsWith('/publish')).length,1);
 } finally {global.window=previousWindow;global.document=previousDocument;}
});

test('criterion shows AI score beside its name, preserves zero and copies it only on teacher action',()=>{
 const suggestion={proposed_score:0,rationale:'Вычисление содержит ошибку.',finding:'concern',interpretation:'Сравните уравнение.',evidence:[],suggested_improvement:'Проверьте знак.',missing_evidence:[],uncertainty:[]};
 const criterion={...lib.reviewCriteria(data)[0],suggestion};
 const {RubricCriterionCard,TeacherDecisionEditor}=load('src/components/review/criterion-card.tsx',{'../../lib/review-workspace':lib});
 let copied=null;const props={criterion,index:0,value:{points:'',feedback:'Мой комментарий',action:'unreviewed'},onChange:patch=>copied=patch,manual:true,busy:false,dirty:false,savedState:'unreviewed'};
 const html=render(React.createElement(RubricCriterionCard,props));
 assert.match(html,/<header[^]*Балл ИИ: 0[^]*<strong>0/);assert.match(html,/Ваш балл/);assert.match(html,/value=""/);
 assert.ok(html.indexOf('Вычисление содержит ошибку.')<html.indexOf('Ваш балл'));
 assert.equal(copied,null);
 // Call with a hook stub to exercise the exact action from the rendered card.
 const card=load('src/components/review/criterion-card.tsx',{react:{...React,useState:init=>[init,()=>{}]},'../../lib/review-workspace':lib}).RubricCriterionCard;
 find(card(props),n=>n.type==='button'&&String(n.props.children).startsWith('Использовать')).props.onClick();
 assert.equal(copied.points,'0');assert.equal(copied.action,'accepted');assert.equal(copied.feedback,undefined);
 copied=null;
 const editor=load('src/components/review/criterion-card.tsx',{react:{...React,useId:()=> 'score'},'../../lib/review-workspace':lib}).TeacherDecisionEditor;
 find(editor({...props,manual:false}),n=>n.type==='button'&&n.props['aria-pressed']===false).props.onClick();
 assert.equal(copied.points,'0');
 const missing=render(React.createElement(RubricCriterionCard,{...props,criterion:{...criterion,suggestion:{...suggestion,proposed_score:null,missing_evidence:['Ответ на задачу 4 отсутствует.']}}}));
 assert.match(missing,/Балл ИИ: не выставлен/);assert.match(missing,/Ответ на задачу 4 отсутствует/);assert.doesNotMatch(missing,/Использовать 0/);
});
