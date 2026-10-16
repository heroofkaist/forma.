const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.filename=name;m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const child of React.Children.toArray(node.props.children)){const result=find(child,predicate);if(result)return result;}}
function harness(){let cursor=0;const state=[],effects=[];const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>v===b[i]);return{hooks:{...React,useState:init=>{const i=cursor++;if(!(i in state))state[i]=typeof init==='function'?init():init;return[state[i],value=>state[i]=typeof value==='function'?value(state[i]):value];},useRef:init=>{const i=cursor++;return state[i]??(state[i]={current:init});},useEffect:(fn,deps)=>{const i=cursor++;if(!same(state[i],deps)){state[i]=deps;effects.push(fn);}}},view(fn){cursor=0;const result=fn();for(const fn of effects.splice(0))fn();return result;}};}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const empty={status:'missing',corpus_key:'corpus',checked:0,compared:0,total:2,remaining:2,coverage_complete:false,skipped:[],pairs:[],documents:[],scope:'Current and previous cohorts.'};
test('archive matches are red evidence flags, preserve a tiny positive match and never declare cheating',()=>{
 const {ArchiveMatchSignal}=require('../src/components/assignment/archive-file-comparison.tsx');
 const value={status:'partial',score:.001,checked:1,total:10,coverage_complete:false,stale:false};
 const html=render(React.createElement(ArchiveMatchSignal,{submissionId:'s',value}));
 assert.match(html,/has-archive-match/);assert.match(html,/&lt;1%/);assert.match(html,/архив проверен не полностью/i);assert.match(html,/\/teacher\/archive\/s#archive-files/);assert.doesNotMatch(html,/точно списал|плагиат доказан/i);
 const unknown=render(React.createElement(ArchiveMatchSignal,{submissionId:'s',value:{...value,score:null}}));assert.doesNotMatch(unknown,/has-archive-match|0%/);
 const stale=render(React.createElement(ArchiveMatchSignal,{submissionId:'s',value:{...value,score:1,stale:true}}));assert.doesNotMatch(stale,/has-archive-match|100%/);
});
test('archive comparison reads without computing, serializes clicks and resumes every missing file',async()=>{
 const h=harness(),calls=[];let checked=0;
 const {ArchiveFileComparison}=load('src/components/assignment/archive-file-comparison.tsx',{react:h.hooks,'../../lib/platform':{platformRequest:async(url,body)=>{calls.push([url,body]);if(body)checked++;return {...empty,checked,compared:checked,remaining:2-checked,coverage_complete:checked===2,status:checked===2?'completed':'partial'};}}});
 let tree;const view=()=>tree=h.view(()=>ArchiveFileComparison({submissionId:'s'}));
 view();await tick();view();assert.equal(calls.filter(c=>c[1]).length,0);
 const button=find(tree,n=>n.type==='button'&&n.props.className==='button primary');button.props.onClick();button.props.onClick();await tick();view();
 assert.equal(calls.filter(c=>c[1]).length,2);assert.ok(calls.filter(c=>c[1]).every(c=>c[1].expected_corpus==='corpus'));assert.equal(find(tree,n=>n.type==='button'&&n.props.className==='button primary').props.disabled,true);
 assert.match(render(tree),/Проверено 2 из 2/);
});
test('switching documents ignores an older in-flight result',async()=>{
 const h=harness();let resolvePost,id='old';
 const {ArchiveFileComparison}=load('src/components/assignment/archive-file-comparison.tsx',{react:h.hooks,'../../lib/platform':{platformRequest:async(url,body)=>body?new Promise(resolve=>resolvePost=resolve):{...empty,checked:url.endsWith('/new')?1:0,corpus_key:url.endsWith('/new')?'new':'old'}}});
 let tree;const view=()=>tree=h.view(()=>ArchiveFileComparison({submissionId:id}));
 view();await tick();view();find(tree,n=>n.type==='button'&&n.props.className==='button primary').props.onClick();await tick();id='new';view();await tick();view();
 resolvePost({...empty,checked:99,remaining:0,coverage_complete:true});await tick();view();assert.match(render(tree),/Проверено 1 из 2/);assert.doesNotMatch(render(tree),/Проверено 99/);
});
test('bulk archive scan updates each student from saved results without launching AI',async()=>{
 const h=harness(),calls=[],updates=[];
 const {ArchiveScanButton}=load('src/components/assignment/archive-file-comparison.tsx',{react:h.hooks,'../../lib/platform':{platformRequest:async(url,body)=>{calls.push([url,body]);return {...empty,remaining:body||url.endsWith('/second')?0:1,checked:2,compared:2,coverage_complete:!!body||url.endsWith('/second')};}}});
 let tree;const view=()=>tree=h.view(()=>ArchiveScanButton({works:[{id:'first',name:'First'},{id:'second',name:'Second'}],onResult:(...args)=>updates.push(args)}));
 view();const start=find(tree,n=>n.type==='button'&&n.props.className==='button');start.props.onClick();start.props.onClick();await tick();view();
 assert.equal(calls.filter(c=>c[1]).length,1);assert.deepEqual(updates.map(u=>u[0]),['first','second']);assert.ok(calls.every(c=>c[0].startsWith('/api/assignment-comparison/archive/')));
});
