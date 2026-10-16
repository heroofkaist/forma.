const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),Module=require('node:module'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup:render}=require('react-dom/server');
function load(file,imports={}){const name=path.resolve(file),m=new Module(name,module);m.filename=name;m.paths=Module._nodeModulePaths(path.dirname(name));const req=m.require.bind(m);m.require=key=>imports[key]??req(key);m._compile(ts.transpileModule(fs.readFileSync(name,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText,name);return m.exports;}
function find(node,predicate){if(!React.isValidElement(node))return;if(predicate(node))return node;for(const c of React.Children.toArray(node.props.children)){const hit=find(c,predicate);if(hit)return hit;}}
const structure=load('src/lib/answer-structure.ts'),editor=load('src/components/task-rubric-editor.tsx');
test('several problem criteria group distinct answers while essay criteria do not duplicate the response',()=>{
 const sections=[{id:'a',question_id:'q',criterion_ids:['c1']},{id:'b',question_id:'q',criterion_ids:['c2']},{id:'u',question_id:null}];
 const groups=[1,2].map(n=>({id:`task${n}`,question_id:'q',mode:'problem_criteria',criterion_ids:[`c${n}`]}));
 const grouped=structure.groupSections(sections,groups);assert.deepEqual(grouped.rows.map(r=>r.sections.map(s=>s.id)),[['a'],['b']]);assert.deepEqual(grouped.unassigned.map(s=>s.id),['u']);
 const essay=structure.groupSections(sections,[{id:'essay',question_id:'q',mode:'whole_work',criterion_ids:['c1','c2']}]);assert.equal(essay.rows.length,1);assert.equal(essay.rows[0].sections.length,2);
});
test('task payload keeps independent maxima and partial-credit instructions',()=>{
 const tasks=[{id:'q1',title:'Force',statement:'Find F',maximum_points:'7',criteria:[{description:'Reasoning',maximum_points:'4',partial_credit:'Correct method with arithmetic error: 2',evidence_expected:'Show Newton law'},{description:'Units',maximum_points:'3'}]},{id:'q2',title:'Energy',statement:'Find E',maximum_points:'3',criteria:[{description:'Conservation',maximum_points:'3'}]}];
 const result=editor.taskPayload(tasks);assert.deepEqual(result.map(q=>q.maximum_points),[7,3]);assert.deepEqual(result.map(q=>q.id),['q1','q2']);assert.equal(result[0].criteria[0].partial_credit,tasks[0].criteria[0].partial_credit);assert.equal(result[0].criteria[0].maximum_points,4);
});
test('task file upload recovers a lost response without uploading a duplicate',async()=>{
 const file=new File(['teacher instructions'],'Task.pdf');let saved=[],calls=0;
 const lib=load('src/lib/assignment-brief.ts',{'./platform':{platformRequest:async()=>({items:saved})},'./api':{API_URL:'/proxy',authenticatedFetch:async(url,options)=>{calls++;assert.equal(url,'/proxy/api/assignment-briefs/a');assert.equal(options.body.get('file').name,'Task.pdf');const hash=Buffer.from(await crypto.subtle.digest('SHA-256',await file.arrayBuffer())).toString('hex');saved=[{id:'brief',content_hash:hash}];throw Error('lost response');}}});
 await assert.rejects(lib.uploadAssignmentBrief('a',file),/lost response/);assert.equal((await lib.uploadAssignmentBrief('a',file)).id,'brief');assert.equal(calls,1);assert.ok(lib.briefFileError({name:'x.exe',size:10}));
});
test('answer overview shows task cards and hides repeated raw fragment editors',()=>{
 const questions=[{id:'q1',title:'Problem 1',criteria:[{criterion_id:'c1',description:'Reasoning',maximum_points:5}]}];
 const groups=[{id:'q1',question_id:'q1',title:'Problem 1',criterion_ids:['c1'],criteria:questions[0].criteria,maximum_points:5}];
 const draft={document_type:'problem_set',sections:[1,2].map(n=>({id:`s${n}`,page_number:n,kind:'answer',question_id:'q1',criterion_ids:['c1'],transcription:'Observed answer',readability:'readable',rationale:'Provider-proposed observation; mathematical interpretation is separate and unverified.',uncertainty_notes:[],evidence_kind:'visual_page'})),warnings:[],question_associations:[],requires_human_review:true};
 let index=0;const values=[questions,groups,[],[],draft,'version',false,false,''];
 const {DocumentAnalysis}=load('src/components/document-analysis.tsx',{react:{...React,useEffect(){},useState:initial=>[values[index++]??initial,()=>{}]},'../lib/presentation':{statusLabel:x=>x},'../lib/platform':{},'../lib/answer-structure':structure});
 const html=render(React.createElement(DocumentAnalysis,{submissionId:'a',questions,onPage(){}}));assert.equal((html.match(/class="answer-group"/g)??[]).length,1);assert.match(html,/Страницы ответа: 1, 2/);assert.match(html,/Reasoning/);assert.match(html,/Исправить распознавание или привязку/);assert.doesNotMatch(html,/Источник 1|Наблюдаемый текст|Provider-proposed/);
});
test('one whole-work question needs no manual page-mapping form',()=>{
 const {QuestionPages}=load('src/components/review/question-review-tools.tsx',{'next/link':{},'../../lib/platform':{},'../../lib/review-pilot':{}});
 const html=render(React.createElement(QuestionPages,{data:{file_type:'pdf',questions:[{id:'q1',title:'Essay'}]},busy:false,onPage(){},onDirty(){}}));assert.match(html,/отдельная разметка не нужна/);assert.doesNotMatch(html,/type="checkbox"|Сохранить страницы/);
});
