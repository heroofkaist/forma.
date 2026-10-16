const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const c of React.Children.toArray(node.props.children)){const hit=find(c,predicate);if(hit)return hit;}}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const imports={'./api':{},'./platform':{}};
test('template policy belongs to the exact assignment and only student-visible files are exposed',()=>{
 const lib=load('src/lib/assignment-template.ts',imports);
 const material={id:'m',file_name:'Worksheet.docx',visibility:'student_visible',tags:'forma:assignment-template:a:required'};
 assert.deepEqual(lib.templateFromMaterials([material],'a'),{id:'m',file_name:'Worksheet.docx',required:true});
 assert.equal(lib.templateFromMaterials([material],'a2'),null);
 assert.equal(lib.templateFromMaterials([{...material,visibility:'teacher_only'}],'a'),null);
 assert.equal(lib.templateFromMaterials([{...material,tags:'forma:assignment-template:a:optional'}],'a').required,false);
 assert.equal(lib.templateFromMaterials([{...material,tags:'Lecture notes'}],'a'),null);
 for(const file of [{name:'x.pdf',size:0},{name:'x.zip',size:10},{name:'x.pdf',size:31*1024*1024}])assert.ok(lib.templateFileError(file));
 assert.equal(lib.templateFileError({name:'Worksheet.DOCX',size:100}),null);
});
test('template upload persists file and required policy and recovers a lost response without another POST',async()=>{
 const calls=[];let saved=[];
 const lib=load('src/lib/assignment-template.ts',{'./api':{API_URL:'/proxy',authenticatedFetch:async(url,opts)=>{calls.push([url,opts]);saved=[{id:'m',file_name:'Template.pdf',visibility:'student_visible',tags:opts.body.get('tags')}];return{ok:true,json:async()=>({id:'m'})};}},'./platform':{platformRequest:async()=>({items:saved})}});
 const file=new File(['synthetic'],'Template.pdf');
 await lib.uploadAssignmentTemplate('offering','a',file,true);
 assert.equal(calls.length,1);assert.equal(calls[0][0],'/proxy/api/course-materials/offering');
 assert.equal(calls[0][1].body.get('visibility'),'student_visible');
 assert.equal(calls[0][1].body.get('tags'),'forma:assignment-template:a:required');
 assert.equal(calls[0][1].body.get('file').name,'Template.pdf');
 assert.equal((await lib.uploadAssignmentTemplate('offering','a',file,true)).id,'m');assert.equal(calls.length,1);
});
test('failed template upload keeps the created assignment and retries attachment without duplicate assignment or double clicks',async()=>{
 const slots=[];let cursor,tree,created=0,uploads=0,completed=0,finish;
 const hooks={...React,useState:init=>{const i=cursor++;if(!(i in slots))slots[i]=init;return[slots[i],v=>{slots[i]=typeof v==='function'?v(slots[i]):v;}];},useRef:init=>{const i=cursor++;return slots[i]??(slots[i]={current:init});}};
 const {AssignmentCreateForm}=load('src/components/assignment-create-form.tsx',{react:hooks,'../lib/assignment-brief':{},'./task-rubric-editor':load('src/components/task-rubric-editor.tsx'),'../lib/assignment-preflight':load('src/lib/assignment-preflight.ts'),'../lib/academic':{academicApi:{createAssignment:async()=>{created++;return{id:'a'};}}},'../lib/assignment-template':{templateFileError:()=>null,uploadAssignmentTemplate:async(...args)=>{uploads++;assert.equal(args[1],'a');assert.equal(args[3],true);if(uploads===1)return await new Promise((resolve,reject)=>{finish={resolve,reject};});}}});
 const props={offeringId:'offering',onCreated:id=>{assert.equal(id,'a');completed++;}};
 const view=()=>render(React.createElement(()=>{cursor=0;tree=AssignmentCreateForm(props);return tree;}));
 view();find(tree,n=>n.type==='input'&&n.props.required&&n.props.type===undefined).props.onChange({target:{value:'Synthetic task'}});view();
 find(tree,n=>n.type==='input'&&n.props['aria-label']==='Файл шаблона').props.onChange({target:{files:[new File(['synthetic'],'Template.pdf')]}});view();
 find(tree,n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked===false).props.onChange({target:{checked:true}});view();
 const submit=()=>find(tree,n=>n.type==='form').props.onSubmit({preventDefault(){}});
 submit();submit();await tick();assert.equal(created,1);assert.equal(uploads,1);assert.equal(completed,0);
 finish.reject(Error('Synthetic upload outage'));await tick();assert.match(view(),/Synthetic upload outage/);
 assert.equal(find(tree,n=>n.type==='fieldset'&&n.props.className==='assignment-create-fields').props.disabled,true);
 assert.match(view(),/Завершить сохранение/);
 await submit();view();assert.equal(created,1);assert.equal(uploads,2);assert.equal(completed,1);
});
