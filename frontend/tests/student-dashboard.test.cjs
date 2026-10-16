const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}) { const filename=path.resolve(file),m=new Module(filename,module);m.paths=Module._nodeModulePaths(path.dirname(filename));const req=m.require.bind(m);m.require=name=>imports[name]??req(name);m._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,filename);return m.exports; }
const dashboard=load('src/lib/student-dashboard.ts'),presentation=load('src/lib/presentation.ts');
test('course search matches names, public codes and instructors, without changing the catalogue',()=>{
 const courses=[{name:'Физика',code:'PHYS101',instructor:'Ирина',offerings:[{id:'physics',term:'Fall',academic_year:'2026'}]},{name:'Алгебра',code:'MATH101',instructor:'Сергей',offerings:[{id:'math',instructor:'Анна'}]}];
 for(const query of [' физика ','phys101','ИРИНА'])assert.equal(dashboard.searchCourses(courses,query)[0].offering.id,'physics');
 assert.equal(dashboard.searchCourses(courses,'анна')[0].offering.id,'math');
 assert.equal(dashboard.searchCourses(courses,'unknown').length,0);assert.equal(dashboard.searchCourses(courses,'').length,2);assert.equal(courses.length,2);
});
test('work filters preserve published zero over AI state and put undated/invalid deadlines last',()=>{
 const items=[{id:'undated',title:'Я',due_at:null},{id:'graded',title:'Published zero',due_at:'2026-10-18',published_at:'2026-10-16',grade:0,submission_status:'overdue'}, {id:'waiting',title:'Waiting',latest_submission:{status:'failed'},due_at:'2026-10-17'}, {id:'due',title:'Due',submission_status:'overdue',due_at:'2026-10-15'}, {id:'invalid',title:'А',due_at:'invalid'}];
 assert.deepEqual(dashboard.dashboardWork(items,'all').map(x=>x.id),['due','waiting','graded','invalid','undated']);
 assert.deepEqual(dashboard.dashboardWork(items,'submitted').map(x=>x.id),['waiting']);
 assert.deepEqual(dashboard.dashboardWork(items,'graded').map(x=>x.id),['graded']);
 assert.deepEqual(dashboard.dashboardWork(items,'todo').map(x=>x.id),['due','invalid','undated']);
 assert.equal(items[0].id,'undated');assert.equal(dashboard.taskCount(1),'1 задание');assert.equal(dashboard.taskCount(2),'2 задания');assert.equal(dashboard.taskCount(11),'11 заданий');assert.equal(dashboard.taskCount(21),'21 задание');
});
function find(node,predicate){if(!React.isValidElement(node))return; if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const found=find(child,predicate);if(found)return found;}}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function enrollmentHarness(request,onJoined=()=>{}) {
 const slots=[];let cursor,tree;
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});}};
 const {CourseEnrollment}=load('src/components/course-enrollment.tsx',{react:hooks,'next/link':{default:({children,...props})=>React.createElement('a',props,children)},'../lib/platform':{platformRequest:request},'../lib/presentation':presentation});
 return {view(){return render(React.createElement(()=>{cursor=0;tree=CourseEnrollment({onJoined});return tree;}));},get tree(){return tree;},input(value){find(tree,n=>n.type==='input').props.onChange({target:{value}});},lookup(){find(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});},join(){find(tree,n=>n.type==='button'&&n.props.type==='button').props.onClick();}};
}
const preview={title:'Synthetic Physics',teacher:'Synthetic Teacher',code:'PHYS101',term:'Fall',academic_year:'2026',offering_id:'synthetic',enrollment_status:'not_enrolled',approval_required:false};
test('enrollment previews before explicit confirmation, normalizes code and blocks duplicate in-flight joins',async()=>{
 const calls=[];let resolveJoin,joined=0;
 const ui=enrollmentHarness(async(path,body)=>{calls.push({path,body});return path.endsWith('/preview')?preview:await new Promise(resolve=>{resolveJoin=resolve;});},()=>{joined++;});
 ui.view();assert.equal(calls.length,0);ui.input(' phys123 ');ui.view();ui.lookup();await tick();
 assert.match(ui.view(),/Synthetic Physics/);assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/enrollment/preview');assert.deepEqual(calls[0].body,{class_code:'PHYS123'});
 ui.join();ui.join();assert.equal(calls.length,2);assert.equal(calls[1].path,'/api/enrollment/join');assert.equal(joined,0);
 assert.match(ui.view(),/Отправляем/);resolveJoin({status:'active'});await tick();
 const html=ui.view();assert.match(html,/Вы записаны на курс/);assert.match(html,/href="\/student\/courses\/synthetic"/);assert.equal(joined,1);
});
test('pending approval never claims access; already-enrolled and blocked students cannot join again',async()=>{
 for(const state of ['active','pending','removed','suspended','rejected','unknown']){
  let calls=0;const ui=enrollmentHarness(async()=>{calls++;return {...preview,enrollment_status:state};});ui.view();ui.input('SYNTH');ui.view();ui.lookup();await tick();const html=ui.view();
  assert.equal(calls,1);assert.equal(find(ui.tree,n=>n.type==='button'&&n.props.type==='button'),undefined);
  if(state==='active')assert.match(html,/Открыть курс/);else assert.doesNotMatch(html,/Открыть курс/);
 }
 let joined=0;const ui=enrollmentHarness(async path=>path.endsWith('/preview')?{...preview,approval_required:true}:{status:'pending'},()=>{joined++;});
 ui.view();ui.input('SYNTH');ui.view();ui.lookup();await tick();assert.match(ui.view(),/Отправить заявку/);ui.join();await tick();assert.match(ui.view(),/Ждём подтверждения/);assert.equal(joined,0);
});
test('enrollment failure retains the code for retry; editing code clears obsolete preview',async()=>{
 let calls=0;const ui=enrollmentHarness(async()=>{if(++calls===1)throw new Error('Синтетическая ошибка');return preview;});
 ui.view();ui.input('SYNTH');ui.view();ui.lookup();await tick();assert.match(ui.view(),/role="alert"/);assert.equal(find(ui.tree,n=>n.type==='input').props.value,'SYNTH');
 ui.lookup();await tick();assert.match(ui.view(),/Synthetic Physics/);ui.input('OTHER');assert.doesNotMatch(ui.view(),/Synthetic Physics|Синтетическая ошибка/);
});
test('dashboard controls filter real loaded rows, show empty results and retry without stale data',async()=>{
 const slots=[];let cursor,tree,start,fail=false;
 const courses=[{id:'course',name:'Synthetic Physics',code:'PHYS',instructor:'Teacher',offerings:[{id:'offering',status:'active',term:'Fall',academic_year:'2026'}]}];
 const work=[{id:'todo',offering_id:'offering',title:'To hand in',submission_status:'not_started',maximum_score:10},{id:'graded',offering_id:'offering',title:'Published zero',published_at:'2026-10-16',grade:0,maximum_score:10,submission_status:'failed'}];
 const hooks={...React,useEffect:effect=>{start??=effect;},useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],value=>{slots[i]=typeof value==='function'?value(slots[i]):value;}];}};
 const {default:Page}=load('src/app/student/page.tsx',{react:hooks,'next/link':{default:({children,...props})=>React.createElement('a',props,children)},'../../components/student-shell':{StudentShell:({children})=>React.createElement('main',null,children)},'../../components/course-enrollment':{CourseEnrollment:()=>null},'../../lib/academic':{academicApi:{courses:async()=>{if(fail)throw new Error('Synthetic outage');return courses;},studentAssignments:async()=>work}},'../../lib/presentation':presentation,'../../lib/student-dashboard':dashboard});
 const view=()=>render(React.createElement(()=>{cursor=0;tree=Page();return tree;}));
 assert.match(view(),/Загружаем курсы/);start();await tick();let html=view();assert.match(html,/0 \/ 10/);assert.match(html,/Оценка опубликована/);
 find(tree,n=>n.type==='button'&&n.props['aria-pressed']===false&&React.Children.toArray(n.props.children)[0]==='Нужно сдать').props.onClick();
 html=view();assert.match(html,/To hand in/);assert.doesNotMatch(html,/Published zero/);
 find(tree,n=>n.type==='input').props.onChange({target:{value:'nothing'}});html=view();assert.match(html,/Курсы не найдены/);assert.doesNotMatch(html,/<h2><a[^>]+>Synthetic Physics/);
 find(tree,n=>n.type==='button'&&n.props.children==='Сбросить поиск').props.onClick();assert.match(view(),/Synthetic Physics/);
 // Enrollment refresh uses the same loading/error/retry path.
 fail=true;find(tree,n=>typeof n.props.onJoined==='function').props.onJoined();await tick();html=view();assert.match(html,/Synthetic outage/);assert.doesNotMatch(html,/Published zero|Synthetic Physics/);
 fail=false;find(tree,n=>n.type==='button'&&n.props.children==='Попробовать снова').props.onClick();await tick();assert.match(view(),/Synthetic Physics/);
});
