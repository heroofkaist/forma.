const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
const preflight=load('src/lib/assignment-preflight.ts'),review=load('src/lib/review-workspace.ts'),pilot=load('src/lib/review-pilot.ts');
function find(node,predicate){if(!React.isValidElement(node))return; if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const hit=find(child,predicate);if(hit)return hit;}}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
test('question queue offers direct mapping for missing and stale pages while keeping ready and unsupported work reviewable',()=>{
 const {QuestionReviewQueue}=load('src/components/review/question-review-queue.tsx',{'next/link':{default:({children,...props})=>React.createElement('a',props,children)},'../../lib/review-pilot':pilot,'../../lib/presentation':load('src/lib/presentation.ts')});
 const base={student_name:'Synthetic student',file_name:'Synthetic.pdf',file_type:'pdf',page_count:3,review_status:'unreviewed',mapping:null};
 const data={questions:[{id:'q2',title:'Second'}],items:[{...base,id:'missing'},{...base,id:'stale',mapping:{id:'map',question_id:'q2',pages:[3],stale:true}},{...base,id:'ready',mapping:{id:'map',question_id:'q2',pages:[2],stale:false}},{...base,id:'unavailable',page_count:0},{...base,id:'docx',file_type:'docx',page_count:0}]};
 const html=render(React.createElement(QuestionReviewQueue,{data,question:'q2'}));
 assert.match(html,/Требуют разметки: 2/);
 for(const id of ['missing','stale'])assert.ok(html.includes(pilot.questionMappingUrl(id,'q2').replaceAll('&','&amp;')));
 assert.ok(html.includes(pilot.questionReviewUrl('ready','q2',[2]).replaceAll('&','&amp;')));
 for(const id of ['ready','unavailable','docx'])assert.ok(!html.includes(pilot.questionMappingUrl(id,'q2').replaceAll('&','&amp;')));
 assert.match(html,/Вопрос изменён/);assert.match(html,/Страницы пока недоступны/);assert.match(html,/Оригинал доступен для скачивания/);
 assert.equal(pilot.questionMappingUrl('s/1','q & 2'),'/teacher/submissions/s%2F1/review?question=q+%26+2&tool=pages#rw-question-pages');
 assert.match(render(React.createElement(QuestionReviewQueue,{data:{...data,items:[]},question:'q2'})),/Работ пока нет/);
});
test('queue mapping entry reveals the selected question, focuses the tool and loads only saved page metadata',async()=>{
 const slots=[],effects=[],requests=[];let cursor,tree,scrolled=false,focused=false;
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useEffect:fn=>{effects.push(fn);},useRef:()=>({current:{scrollIntoView:()=>{scrolled=true;},querySelector:()=>({focus:()=>{focused=true;}})}})};
 const {QuestionPages}=load('src/components/review/question-review-tools.tsx',{react:hooks,'next/link':{},'../../lib/review-pilot':pilot,'../../lib/platform':{platformRequest:async(...args)=>{requests.push(args);return{items:[{id:'map',question_id:'q2',pages:[2],stale:false}]};}}});
 const props={data:{submission_id:'s',file_type:'pdf',questions:[{id:'q1',title:'One'},{id:'q2',title:'Two'}],structure:{pages:[{number:1},{number:2}]}},busy:false,onPage:()=>{},onDirty:()=>{},initialQuestionId:'q2',reveal:true};
 const view=()=>render(React.createElement(()=>{cursor=0;effects.length=0;tree=QuestionPages(props);return tree;}));
 view();assert.equal(tree.props.open,true);assert.equal(requests.length,0);effects[2]();await tick();view();
 assert.equal(scrolled,true);assert.equal(focused,true);assert.deepEqual(requests,[['/api/review-pilot/submissions/s/pages']]);
 assert.equal(find(tree,n=>n.type==='select').props.value,'q2');
 assert.equal(find(tree,n=>n.type==='input'&&n.props.checked===true).props.type,'checkbox');
});
test('assignment preflight distinguishes invalid dates/scores from incomplete rubric warnings',()=>{
 const form={title:'Synthetic task',maximum_score:'10',available_at:'2026-10-16T09:00',due_at:'2026-10-17T09:00'};
 assert.deepEqual(preflight.assignmentPreflight(form,[{description:'Method',maximum_points:'10'}]).errors,[]);
 for(const change of [{title:' '},{maximum_score:'NaN'},{maximum_score:'0'},{maximum_score:'10001'},{due_at:form.available_at},{due_at:'invalid'},{due_at:'2026-10-15T09:00'}])assert.ok(preflight.assignmentPreflight({...form,...change},[]).errors.length);
 assert.ok(preflight.assignmentPreflight(form,[{description:'Method',maximum_points:'11'}]).errors.length);
 assert.ok(preflight.assignmentPreflight(form,[{description:'Method',maximum_points:'Infinity'}]).errors.length);
 assert.equal(preflight.assignmentPreflight(form,[{description:'Method',maximum_points:'5'}]).warnings.length,1);
 assert.equal(preflight.assignmentPreflight(form,[]).warnings.length,1);
});
test('card provenance survives manual and assisted save payloads without initializing points',()=>{
 const card_use={card_id:'c',evidence:{page_number:2,observation:'Teacher checked the original'}};
 const data={questions:[{id:'q',criteria:[{criterion_id:'c',description:'Method',maximum_points:10}]}],reviews:[{id:'r',created_at:'2026-10-16',criteria:[{question_id:'q',criterion_id:'c',points:null,comment:'Saved explanation',confirmed:false,card_use}],feedback:''}],published_grade:null};
 const editor=review.initialEditor(data);const criteria=review.reviewCriteria(data);
 assert.equal(Object.values(editor.criteria)[0].points,'');assert.deepEqual(review.manualPayload(criteria,editor)[0].card_use,card_use);
 editor.mode='assisted';Object.values(editor.criteria)[0].action='accepted';assert.deepEqual(review.decisionsPayload(criteria,editor)[0].card_use,card_use);assert.equal(review.completeScores(criteria,editor),false);
 assert.equal(pilot.questionReviewUrl('s','q one',[3,4]),'/teacher/submissions/s/review?question=q+one&page=3');
});
test('decision memory loads only on request and reuses explanation with fresh evidence, never a score',async()=>{
 const state=[];let cursor,tree,patch;const requests=[];
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in state))state[i]=init;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v;}];}};
 const {DecisionMemory}=load('src/components/review/decision-memory.tsx',{react:hooks,'next/link':{default:({children,...props})=>React.createElement('a',props,children)},'../../lib/review-pilot':pilot,'../../lib/platform':{platformRequest:async url=>{requests.push(url);return{items:[{id:'card',title:'Units',kind:'reference',rule:'Use units',feedback:'Explain the units',points:9,evidence:{page_number:1,observation:'Old example'},source_submission_id:'old',created_by:'Teacher'}]};}}});
 const criterion={key:'criterion',question_id:'q',criterion_id:'c',description:'Units',maximum_points:10};
 const props={data:{submission_id:'new',file_type:'pdf',structure:{pages:[{number:1}]},reviews:[]},criteria:[criterion],editor:{criteria:{criterion:{points:'',feedback:'',action:'unreviewed'}}},busy:false,onApply:(key,value)=>{patch={key,value};}};
 const view=()=>render(React.createElement(()=>{cursor=0;tree=DecisionMemory(props);return tree;}));
 view();assert.equal(requests.length,0);find(tree,n=>n.type==='button'&&n.props.children==='Найти совместимые карточки').props.onClick();await tick();let html=view();assert.match(html,/Ориентир/);
 let apply=find(tree,n=>n.type==='button'&&n.props.children==='Применить с новым основанием');assert.equal(apply.props.disabled,true);
 find(tree,n=>n.type==='textarea').props.onChange({target:{value:'Fresh evidence on this original'}});view();apply=find(tree,n=>n.type==='button'&&n.props.children==='Применить с новым основанием');assert.equal(apply.props.disabled,false);apply.props.onClick();
 assert.equal(patch.key,'criterion');assert.equal(patch.value.feedback,'Explain the units');assert.equal(patch.value.points,undefined);assert.equal(patch.value.action,undefined);assert.deepEqual(patch.value.card_use,{card_id:'card',evidence:{page_number:1,observation:'Fresh evidence on this original'}});
});
test('question-only view keeps other rubric values in a complete draft payload',()=>{
 const data={questions:[{id:'q1',criteria:[{criterion_id:'c1',description:'One',maximum_points:5}]},{id:'q2',criteria:[{criterion_id:'c2',description:'Two',maximum_points:5}]}],reviews:[]};
 const criteria=review.reviewCriteria(data),editor=review.initialEditor(data);editor.criteria[criteria[0].key].points='0';
 const payload=review.manualPayload(criteria,editor);assert.equal(payload.length,2);assert.equal(payload[0].points,0);assert.equal(payload[1].points,null);assert.equal(review.completeScores(criteria,editor),false);
});

test('reusing an existing explanation does not duplicate its paragraph',()=>{assert.equal(pilot.appendCardExplanation('Same explanation','Same explanation'),'Same explanation');assert.equal(pilot.appendCardExplanation('First\n\nSecond','Second'),'First\n\nSecond');assert.equal(pilot.appendCardExplanation('First','Second'),'First\n\nSecond');});

test('page mapping retains edits on conflict and reports unsaved state until save or explicit reset',async()=>{
 const state=[],effects=[];let cursor,tree,dirty=false,failSave=true;const requests=[];
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in state))state[i]=init;return[state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v;}];},useEffect:fn=>{effects.push(fn);}};
 const {QuestionPages}=load('src/components/review/question-review-tools.tsx',{react:hooks,'next/link':{default:({children,...props})=>React.createElement('a',props,children)},'../../lib/review-pilot':pilot,'../../lib/platform':{platformRequest:async(url,body)=>{
  requests.push({url,body});if(!body)return{items:[{id:'old',question_id:'q1',pages:[1],stale:false}]};
  if(failSave)throw Error('Page mapping changed');return{id:'new',question_id:body.question_id,pages:body.pages,stale:false};
 }}});
 const props={data:{submission_id:'s',file_type:'pdf',questions:[{id:'q1',title:'One'},{id:'q2',title:'Two'}],structure:{pages:[{number:1},{number:2}]}},busy:false,onPage:()=>{},onDirty:value=>{dirty=value;}};
 function view(){effects.length=0;const html=render(React.createElement(()=>{cursor=0;tree=QuestionPages(props);return tree;}));effects[0]();return html;}
 const button=label=>find(tree,n=>n.type==='button'&&n.props.children===label);
 view();await button('Загрузить разметку').props.onClick();view();assert.equal(dirty,false);
 find(tree,n=>n.type==='input'&&n.props.checked===false).props.onChange({target:{checked:true}});view();assert.equal(dirty,true);
 assert.equal(find(tree,n=>n.type==='select').props.disabled,true);assert.equal(button('Перезагрузить разметку').props.disabled,true);
 await button('Сохранить страницы').props.onClick();await tick();assert.match(view(),/Page mapping changed/);assert.equal(dirty,true);
 assert.equal(find(tree,n=>n.type==='input'&&n.props.checked===false),undefined);assert.deepEqual(requests.at(-1).body.pages,[1,2]);assert.equal(requests.at(-1).body.expected_mapping_id,'old');
 button('Отменить изменения разметки').props.onClick();view();assert.equal(dirty,false);
 find(tree,n=>n.type==='input'&&n.props.checked===false).props.onChange({target:{checked:true}});view();failSave=false;
 await button('Сохранить страницы').props.onClick();await tick();assert.match(view(),/Страницы вопроса сохранены/);assert.equal(dirty,false);
});

test('student upload requires both checks, serializes clicks, reuses retry key and preserves an accepted receipt on refresh failure',async()=>{
 const slots=[];let cursor,tree,start,finish;const calls=[];
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});},useEffect:fn=>{start??=fn;}};
 let reads=0;
 const {default:Page}=load('src/app/student/assignments/[assignmentId]/page.tsx',{
  react:hooks,'next/navigation':{useParams:()=>({assignmentId:'a'})},'next/link':{default:({children,...props})=>React.createElement('a',props,children)},
  '../../../../components/student-shell':{StudentShell:({children})=>React.createElement('main',null,children)},
  '../../../../components/submission-gate':load('src/components/submission-gate.tsx'),
  '../../../../components/published-result':{PublishedResult:()=>null},
  '../../../../lib/platform':{},'../../../../lib/presentation':load('src/lib/presentation.ts'),
  '../../../../lib/academic':{academicApi:{assignment:async()=>{if(++reads>1)throw Error('refresh outage');return{id:'a',offering_id:'o',title:'Synthetic task',assignment_type:'essay',maximum_score:10,questions:[],allow_resubmission:false};},offering:async()=>({code:'SYNTH'}),submit:async(...args)=>{calls.push(args);return await new Promise((resolve,reject)=>{finish={resolve,reject};});}}},
 });
 const view=()=>render(React.createElement(()=>{cursor=0;tree=Page();return tree;}));
 const upload=()=>find(tree,n=>n.type==='button'&&n.props.className==='button primary full-button');
 view();start();await tick();view();const file={name:'Synthetic.docx',size:100,type:'application/octet-stream'};
 find(tree,n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[file]}});view();assert.equal(upload().props.disabled,true);
 find(tree,n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props.checked).props.onChange({target:{checked:true}});view();assert.equal(upload().props.disabled,true);
 find(tree,n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props.checked).props.onChange({target:{checked:true}});view();assert.equal(upload().props.disabled,false);
 upload().props.onClick();upload().props.onClick();view();assert.equal(calls.length,1);assert.equal(find(tree,n=>n.type==='input'&&n.props.type==='file').props.disabled,true);
 finish.reject(Error('network timeout'));await tick();assert.match(view(),/network timeout/);assert.equal(upload().props.disabled,false);
 upload().props.onClick();view();assert.equal(calls.length,2);assert.equal(calls[0][2],calls[1][2]);assert.match(calls[0][2],/^[a-f0-9-]{36}$/);assert.equal(calls[0][1],file);
 finish.resolve({id:'receipt',file_name:'Synthetic.docx',status:'submitted'});await tick();const html=view();assert.match(html,/Квитанция: receipt/);assert.match(html,/Работа сохранена/);assert.match(html,/Повторная отправка не разрешена/);
});
