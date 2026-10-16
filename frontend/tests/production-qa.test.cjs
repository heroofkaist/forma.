const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const ts = require('typescript');
const React = require('react');
const {renderToStaticMarkup: render} = require('react-dom/server');
function load(source, imports = {}) {
  const filename = path.resolve(source), compiled = new Module(filename, module);
  compiled.paths = Module._nodeModulePaths(path.dirname(filename));
  const original = compiled.require.bind(compiled);
  compiled.require = name => imports[name] ?? original(name);
  compiled._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022,
  }}).outputText, filename);
  return compiled.exports;
}
const similarity = load('src/lib/similarity.ts');
const status = load('src/lib/submission-status.ts');
const review = load('src/lib/review-workspace.ts');
const insights = load('src/lib/teaching-insights.ts');
const {TeachingInsightsContent} = load('src/components/review/teaching-insights.tsx', {
  '../../lib/platform': {}, '../../lib/review-workspace': review, '../../lib/teaching-insights': insights,
});
const body = () => ({submission_id:'s', analysis:{analysis_status:'completed', match_ratio:0, eligible_token_count:10,
  candidate_count:1, extracted_text:'ten words available for comparison', document_title:'Synthetic.pdf'}, items:[]});
test('similarity missing, failed, pending, insufficient and incomplete never become successful zero', () => {
  for (const state of ['missing','failed','queued','analyzing','insufficient_text','disabled','no_sources','incomplete']) {
    const raw = body(); raw.analysis.analysis_status = state;
    const value = similarity.normalizeSimilarityResult(raw).analysis;
    assert.equal(value.matched_text_ratio, null); assert.equal(similarity.similarityPercent(value),'—');
    assert.deepEqual(value.matches,[]);
  }
  const raw = body(); delete raw.analysis;
  assert.equal(similarity.normalizeSimilarityResult(raw).analysis.analysis_status,'missing');
  for (const mutation of [{eligible_token_count:0}, {extracted_text:''}, {match_ratio:null}, {candidate_count:0}, {match_ratio:NaN}]) {
    const raw=body(); Object.assign(raw.analysis,mutation);
    assert.equal(similarity.similarityPercent(similarity.normalizeSimilarityResult(raw).analysis),'—');
  }
});
test('only a completed comparison with eligible sources produces zero; positive reports retain source identity',()=>{
  assert.equal(similarity.similarityPercent(similarity.normalizeSimilarityResult(body()).analysis),'0%');
  const raw=body(); raw.analysis.match_ratio=0.8;
  raw.items=[{id:'pair',submission_id:'s',candidate_submission_id:'source',analysis_status:'completed',match_ratio:0.8,
    eligible_token_count:10,matched_token_count:8,extracted_text:'abcdefghij',teacher_notes:'Saved human context',
    evidence:[{source_offsets:{start:0,end:8},candidate_offsets:{start:4,end:12},source_excerpt:'abcdefgh',candidate_excerpt:'abcdefgh'}]}];
  const value=similarity.normalizeSimilarityResult(raw);
  assert.equal(similarity.similarityPercent(value.analysis),'80%');
  assert.equal(value.analysis.matches[0].report_id,'pair');
  assert.equal(value.analysis.matches[0].source_submission_id,'source');
  assert.equal(value.reports[0].teacher_notes,'Saved human context');
  raw.items[0].eligible_token_count=0;
  assert.equal(similarity.similarityPercent(similarity.normalizeSimilarityResult(raw).analysis),'—');
  assert.deepEqual(similarity.codePointPassage('😀АБВГД',1,4),['😀','АБВ','ГД']);
});
test('server-rendered initial similarity page has loading state without metrics, conclusions or decision actions',()=>{
  const {default: Page}=load('src/app/teacher/submissions/[submissionId]/originality/page.tsx',{
    'next/navigation':{useParams:()=>({submissionId:'s'})}, '../../../../../lib/academic':{},
    '../../../../../lib/similarity':similarity,
    '../../../../../components/app-shell':{AppShell:({children})=>React.createElement('main',null,children)},
  });
  const html=render(React.createElement(Page));
  assert.match(html,/Загружаем отчёт/); assert.doesNotMatch(html,/0%|Значимых совпадений|Сохранить проверку|Итог проверки/);
});
test('human status is primary for every AI state, including explicit published zero and newer drafts',()=>{
  for(const ai of ['not_scheduled','failed','queued','completed']) {
    for(const human of ['unreviewed','draft','confirmed','published']) {
      const item={review_status:human,review_points:['confirmed','published'].includes(human)?0:null,review_maximum:10,has_draft:true,processing_status:ai};
      const label=status.humanReviewLabel(item);
      assert.doesNotMatch(label,/ИИ|анализ/);
      if(human==='published') assert.equal(label,'Опубликована студенту · 0 / 10');
      if(human==='confirmed') assert.match(label,/подтверждена · 0 \/ 10 · не опубликована/);
      assert.match(status.aiProcessingLabel(ai),/^ИИ:/);
    }
  }
});
test('published and confirmed manual editor labels stay authoritative until a new saved draft exists',()=>{
  const data={reviews:[{id:'r',criteria:[{points:0,confirmed:true}]}],published_grade:{review_id:'r'}};
  assert.equal(review.editorSavedState(data,undefined,'manual'),'published');
  data.published_grade=null;
  assert.equal(review.editorSavedState(data,undefined,'manual'),'confirmed');
  data.reviews[0].criteria[0].confirmed=false;
  assert.equal(review.editorSavedState(data,undefined,'manual'),'draft');
  const {ReviewActionBar}=load('src/components/review/review-action-bar.tsx',{'../../lib/review-workspace':review});
  const html=render(React.createElement(ReviewActionBar,{savedState:'published',dirty:false,total:0,maximum:10,hasSaved:true}));
  assert.match(html,/Опубликовано: 0 \/ 10/); assert.doesNotMatch(html,/Черновик: 0/);
});
test('teaching insights load, fail, retry and refresh without preserving stale metrics',async()=>{
  const states=[];
  await insights.loadTeachingInsights(async()=>{throw new Error('network');},s=>states.push(s));
  assert.deepEqual(states.map(s=>s.status),['loading','error']);
  assert.equal(states[1].data,null);
  await insights.loadTeachingInsights(async()=>({items:[],denominator:'server wording'}),s=>states.push(s));
  assert.deepEqual(states.slice(2).map(s=>s.status),['loading','loaded']);
  const empty=render(React.createElement(TeachingInsightsContent,{state:states.at(-1)}));
  assert.match(empty,/Подтверждённых наблюдений пока нет/); assert.doesNotMatch(empty,/\{"items"|server wording/);
  const data={items:[{category:'essay',tag:'argument',confirmed_concerns:1,reviewed_submissions:2,evidence:[{
    submission_id:'s',decision_id:'d',criterion_id:'c',source:[{page_number:2,quote:'<script>synthetic evidence</script>'}],
  }]}],denominator:'Distinct submissions'};
  await insights.loadTeachingInsights(async()=>data,s=>states.push(s));
  const html=render(React.createElement(TeachingInsightsContent,{state:states.at(-1)}));
  assert.match(html,/Эссе · argument/); assert.match(html,/<strong>1<\/strong> из <strong>2<\/strong>/);
  assert.match(html,/\/teacher\/submissions\/s\/review\?page=2/); assert.match(html,/&lt;script&gt;/);
  assert.doesNotMatch(html,/<script>|Distinct submissions/);
  const error=render(React.createElement(TeachingInsightsContent,{state:{status:'error',data:null}}));
  assert.match(error,/role="alert"/); assert.doesNotMatch(error,/Подтверждённых наблюдений пока нет/);
  await insights.loadTeachingInsights(async()=>({items:[{...data.items[0],confirmed_concerns:5}]}),s=>states.push(s));
  assert.equal(states.at(-1).status,'error');
});
test('review history heading identifies student scope rather than course-wide analytics',()=>{
  let hook=0;
  const {AssessmentDiagnostics}=load('src/components/review/assessment-diagnostics.tsx',{
    react:React,
    'next/link':{default:({children,...props})=>React.createElement('a',props,children)},
    '../../lib/presentation':load('src/lib/presentation.ts'),
    './teaching-insights':{TeachingInsights:()=>null},'../document-analysis':{DocumentAnalysis:()=>null},'../../lib/platform':{},
  });
  const html=render(React.createElement(AssessmentDiagnostics,{submissionId:'s',data:{assignment_id:'a',reviews:[]},assessment:null,selected:'',dirty:false,section:'student'}));
  assert.match(html,/<h4>Подтверждённые наблюдения о студенте в курсе<\/h4>/);
  assert.doesNotMatch(html,/Подтверждённые наблюдения по курсу/);
});
test('shared assignment form exposes type, dates, resubmission and teacher rubric with existing styles',()=>{
  const {AssignmentCreateForm}=load('src/components/assignment-create-form.tsx',{'../lib/assignment-template':{},'../lib/academic':{}, '../lib/assignment-preflight':load('src/lib/assignment-preflight.ts')});
  const html=render(React.createElement(AssignmentCreateForm,{offeringId:'synthetic',onCreated:()=>{}}));
  for(const label of ['Тип','Доступно с','Срок сдачи','Макс. балл','Разрешить повторную отправку','Критерии оценивания']) assert.ok(html.includes(label),label);
  assert.match(html,/academic-create-form/);
  // Browser validation uses min as the step base: min=.1, step=.5 rejects the default 100.
  const inputs=[...html.matchAll(/<input[^>]*type="number"[^>]*>/g)].map(m=>m[0]);
  for(const input of inputs) {
    const value=Number(input.match(/value="([^"]+)"/)?.[1]);
    const min=Number(input.match(/min="([^"]+)"/)?.[1] ?? 0);
    const step=input.match(/step="([^"]+)"/)?.[1] ?? '1';
    assert.ok(value>=min);
    if(step!=='any') assert.ok(Math.abs((value-min)/Number(step)-Math.round((value-min)/Number(step)))<1e-8);
  }
});
