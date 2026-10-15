const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const Module = require('node:module');
const path = require('node:path');
const filename = path.resolve('src/lib/review-workspace.ts');
const loaded = new Module(filename, module);
loaded._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText, filename);
const { initialEditor, reviewCriteria, criterionKey, scoreError, completeScores, manualPayload, decisionsPayload, canPublish, shortSummary } = loaded.exports;
function fixture() {
 const data = {title:'Synthetic',assignment_id:'a',maximum_score:10,questions:[{id:'q',title:'Work',criteria:[{criterion_id:'a',description:'Argument',maximum_points:5},{criterion_id:'b',description:'Evidence',maximum_points:5}]}],reviews:[],published_grade:null};
 const spec={category:'essay',instructions:'Teacher instructions',reference_material:'',criteria:data.questions[0].criteria.map(c=>({...c,question_id:'q'}))};
 const version={id:'v',rubric:{id:'r',spec},decisions:[],result:{criteria:spec.criteria.map(c=>({...c,proposed_score:5,suggested_improvement:'AI text',interpretation:'Saved model interpretation',finding:'strength',evidence:[]}))}};
 return {data,version};
}
test('AI scores and feedback never initialize teacher inputs',()=>{
 const {data,version}=fixture(); const editor=initialEditor(data,version);
 assert.equal(editor.mode,'assisted'); assert.deepEqual(Object.values(editor.criteria).map(c=>[c.points,c.feedback,c.action]),[['','','unreviewed'],['','','unreviewed']]);
 assert.equal(completeScores(reviewCriteria(data,version),editor),false); assert.equal(canPublish(data),false);
});
test('explicit zero differs from an ungraded empty input',()=>{
 const {data}=fixture(); const editor=initialEditor(data); const criteria=reviewCriteria(data); editor.criteria[criteria[0].key].points='0';
 assert.equal(manualPayload(criteria,editor)[0].points,0); assert.equal(manualPayload(criteria,editor)[1].points,null); assert.equal(completeScores(criteria,editor),false);
});
test('invalid or incomplete scores are not publishable',()=>{
 for(const value of ['NaN','Infinity','-1','6']) assert.ok(scoreError(value,5));
 for(const value of ['','0','2.5','5']) assert.equal(scoreError(value,5),null);
 const {data}=fixture(); data.reviews=[{id:'r',criteria:[{question_id:'q',criterion_id:'a',points:0},{question_id:'q',criterion_id:'b',points:null}]}];
 assert.equal(canPublish(data),false); data.reviews[0].criteria[1].points=5; assert.equal(canPublish(data),true); data.reviews[0].criteria[1].points=6; assert.equal(canPublish(data),false);
});
test('drafts reload with teacher input and remain unconfirmed',()=>{
 const {data,version}=fixture(); version.decisions=[{id:'d',created_at:'2026-10-15T00:00:00Z',review_id:null,decisions:[{question_id:'q',criterion_id:'a',action:'accepted',points:2,feedback:'Teacher words',finding:'concern',confirmed:false,overall_feedback:'Overall draft'}]}];
 const editor=initialEditor(data,version); const criteria=reviewCriteria(data,version);
 assert.equal(editor.criteria[criterionKey('q','a')].points,'2'); assert.equal(editor.feedback,'Overall draft'); assert.equal(criteria[0].saved.confirmed,false);
 const payload=decisionsPayload(criteria,editor); assert.equal(payload[0].feedback,'Teacher words'); assert.equal('confirmed' in payload[0],false); assert.equal(payload[1].action,'deferred');
});
test('a newer manual review supersedes older AI-assisted scores',()=>{
 const {data,version}=fixture(); version.decisions=[{created_at:'2026-10-14T00:00:00Z',review_id:'old',decisions:[]}];
 data.reviews=[{id:'new',created_at:'2026-10-15T00:00:00Z',feedback:'Manual feedback',criteria:[{question_id:'q',criterion_id:'a',points:0,comment:'Teacher comment'}]}];
 const editor=initialEditor(data,version); assert.equal(editor.mode,'manual'); assert.equal(editor.criteria[criterionKey('q','a')].points,'0'); assert.equal(editor.feedback,'Manual feedback');
});
test('stale rubric limits cannot supply current suggestions',()=>{
 const {data,version}=fixture(); version.rubric.spec.criteria[0].maximum_points=20; assert.equal(reviewCriteria(data,version)[0].suggestion,null);
});
test('one subject-independent view model covers all three categories',()=>{
 for(const category of ['problem_set','essay','lab_report']){const {data,version}=fixture(); version.rubric.spec.category=category; assert.equal(reviewCriteria(data,version).length,2);}
 assert.notEqual(criterionKey('q:a','b'),criterionKey('q','a:b'));
});
test('summaries are bounded without changing saved model content',()=>{
 const source={interpretation:'x'.repeat(500),finding:'concern'}; assert.ok(shortSummary(source).length<=155); assert.equal(source.interpretation.length,500);
});

test('draft manual records and mismatched AI decisions cannot publish an older review',()=>{
 const {data,version}=fixture(); data.reviews=[{id:'manual',criteria:[{question_id:'q',criterion_id:'a',points:2,confirmed:false},{question_id:'q',criterion_id:'b',points:4,confirmed:false}]}];
 assert.equal(canPublish(data),false);
 for(const c of data.reviews[0].criteria) c.confirmed=true;
 assert.equal(loaded.exports.publicationReady(data,version,'assisted'),false);
 assert.equal(loaded.exports.publicationReady(data,version,'manual'),true);
 version.decisions=[{review_id:'manual',decisions:[{confirmed:true}]}];
 assert.equal(loaded.exports.publicationReady(data,version,'assisted'),true);
 version.decisions[0].review_id=null;
 assert.equal(loaded.exports.publicationReady(data,version,'assisted'),false);
});
