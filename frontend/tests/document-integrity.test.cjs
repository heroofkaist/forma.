const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
const lib=load('src/lib/assignment-workspace.ts'),integrity=load('src/lib/document-integrity.ts'),link={default:({children,...props})=>React.createElement('a',props,children)};
const metric=score=>({status:'completed',score,evidence:[]});
const result={status:'completed',stale:false,documents:[{id:'a',student_id:'one',file_name:'First.pdf',units_total:2},{id:'b',student_id:'two',file_name:'Second.pdf',units_total:4}],pairs:[{submission_id:'a',candidate_id:'b',metrics:{document:metric(.75),text:metric(.4),visual:metric(.75),semantic:{...metric(1),source_evidence:[{concept:'force',current:{unit:1,quote:'<script>source</script>'},candidate:{unit:2,quote:'second original passage'}}]}}}]};
test('AI detector never presents an uncalibrated probability or converts a missing analysis to zero',()=>{
 for(const status of ['not_analyzed','failed','awaiting_budget','no_readable_text','input_limit','stale'])assert.doesNotMatch(integrity.detectorLabel({status}),/0%|100%|человек|ИИ написал/);
 assert.equal(integrity.detectorLabel({status:'completed',detector_status:'advisory',signal_count:0}),'Неопределённо');
 assert.equal(integrity.detectorLabel({status:'completed',detector_status:'not_applicable'}),'Не применим к этой работе');
 assert.match(integrity.INTEGRITY_NOTE,/единственное основание/);
});
test('student similarity uses current file results and preserves a real zero without showing stale or unsupported results',()=>{
 assert.deepEqual(lib.fileMatchFor('a',result),{score:.75,candidateId:'b'});
 assert.equal(lib.fileMatchFor('a',{...result,stale:true}),null);
 assert.equal(lib.fileMatchFor('missing',result),null);
 assert.equal(lib.fileMatchFor('a',{...result,pairs:[{...result.pairs[0],metrics:{document:metric(NaN)}}]}),null);
 assert.equal(lib.fileMatchFor('a',{...result,pairs:[{...result.pairs[0],metrics:{document:metric(0)}}]}).score,0);
});
test('whole-file report keeps Qwen concepts separate from file percentage and links evidence to both originals',()=>{
 const {ComparisonReport}=load('src/components/assignment/comparison-report.tsx',{'next/link':link,'../../lib/assignment-workspace':lib});
 const html=render(React.createElement(ComparisonReport,{result}));
 for(const text of ['75%','40%','Содержание · Qwen','First.pdf','Second.pdf','2 стр. / разделов','4 стр. / разделов'])assert.ok(html.includes(text),text);
 assert.match(html,/\/teacher\/compare\/a\/b/);assert.match(html,/review\?page=2/);assert.match(html,/&lt;script&gt;source&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('register renders separate file similarity and AI detector for each submitted work',()=>{
 const {IntegritySignal}=load('src/components/assignment/integrity-signal.tsx',{'next/link':link,'../../lib/platform':{},'../../lib/document-integrity':integrity});
 const {AssignmentRegister}=load('src/components/assignment/assignment-workspace.tsx',{'next/link':link,'./integrity-signal':{IntegritySignal},'../../lib/document-integrity':integrity,'../assignment-template':{},'../assignment-briefs':{},'./comparison-panel':{},'../../lib/api':{},'../../lib/platform':{},'../../lib/submission-status':load('src/lib/submission-status.ts'),'../../lib/assignment-workspace':lib});
 const data={students:[{student_id:'one',student_name:'Ada',active:true}],items:[{id:'a',student_id:'one',file_name:'First.pdf',file_type:'pdf',submitted_at:'2026-10-16',review_status:'unreviewed',processing_status:'not_scheduled',integrity:{status:'not_analyzed'},similarity:{analysis_status:'missing',match_ratio:null}}]};
 const html=render(React.createElement(AssignmentRegister,{data,comparison:result}));assert.match(html,/<th>СХОДСТВО<\/th><th>AI DETECTOR<\/th>/);assert.match(html,/75%/);assert.match(html,/Не запускался/);assert.match(html,/\/teacher\/compare\/a\/b/);assert.match(html,/AI detector может ошибаться/);
});
test('side-by-side view opens PDF pages and readable Office sections without claiming rendered Office layouts',()=>{
 for(const file_type of ['pdf','docx']){
  const source={student_name:'Ada',file_name:`Source.${file_type}`,file_type,structure:{pages:[{number:1,text:'A source passage <script>untrusted</script>'}]}};
  const {default:Compare}=load('src/app/teacher/compare/[leftId]/[rightId]/page.tsx',{
   react:{...React,useEffect(){},useState:initial=>[initial===null?source:initial,()=>{}]},
   'next/link':link,'next/navigation':{useParams:()=>({leftId:'a',rightId:'b'})},
   '../../../../../components/app-shell':{AppShell:({children})=>React.createElement('main',null,children)},
   '../../../../../components/review/document-viewer':{DocumentViewer:({submissionId})=>React.createElement('div',null,`PDF original ${submissionId}`)},
   '../../../../../lib/platform':{},'../../../../../lib/api':{}
  });
  const html=render(React.createElement(Compare));
  assert.match(html,/Source\./);assert.match(html,/\/teacher\/submissions\/a\/review/);assert.match(html,/\/teacher\/submissions\/b\/review/);
  if(file_type==='pdf'){assert.match(html,/PDF original a/);assert.match(html,/PDF original b/);}
  else{assert.match(html,/A source passage &lt;script&gt;untrusted&lt;\/script&gt;/);assert.match(html,/Скачать оригинал/);assert.match(html,/Извлечённое содержимое/);assert.doesNotMatch(html,/PDF original|<script>/);}
 }
});
