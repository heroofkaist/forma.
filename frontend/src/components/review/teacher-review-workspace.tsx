"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FileCheck } from "lucide-react";
import { platformRequest } from "../../lib/platform";
import { editorSavedState, publicationReady, completeScores, editorErrors, initialEditor, manualPayload, reviewCriteria, decisionsPayload } from "../../lib/review-workspace";
import type { AssessmentResponse, EditorValue, ReviewEditor, ReviewResponse } from "../../lib/review-workspace";
import { RubricReviewPanel } from "../assessment-panel";
import {TeachingGuide} from "../assignment/teaching-guide";
import {RevisionContext} from "./revision-context";
import {scoreLabel} from "../../lib/teacher-display";
import type {EvidenceHighlight} from "./document-viewer";
import type {CriterionView} from "../../lib/review-workspace";
import { DocumentViewer } from "./document-viewer";
import { SubmissionOverview } from "./submission-overview";
import { ReviewActionBar } from "./review-action-bar";
import { DecisionMemory } from "./decision-memory";
import { QuestionPages, QuestionReviewNavigation } from "./question-review-tools";
import { ReviewToolsMenu, type ReviewTool } from "./review-tools";
import { AssessmentDiagnostics } from "./assessment-diagnostics";

function ReviewDialog({ title, children, onClose, onConfirm, confirmLabel }: { title: string; children: React.ReactNode; onClose: () => void; onConfirm: () => void; confirmLabel: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current!; const previous = document.activeElement as HTMLElement | null; dialog.showModal(); return () => { dialog.close(); previous?.focus(); }; }, []);
  return <dialog ref={ref} className="rw-dialog" aria-labelledby="review-dialog-title" onCancel={e => { e.preventDefault(); onClose(); }}><h2 id="review-dialog-title">{title}</h2>{children}<div className="rw-dialog-actions"><button className="rw-button" onClick={onClose} autoFocus>Отмена</button><button className="rw-button rw-primary" onClick={onConfirm}>{confirmLabel}</button></div></dialog>;
}
export function TeacherReviewWorkspace({ submissionId }: { submissionId: string }) {
  const router = useRouter(); const [data, setData] = useState<ReviewResponse | null>(null); const [assessment, setAssessment] = useState<AssessmentResponse | null>(null);
  const [editor, setEditor] = useState<ReviewEditor | null>(null); const [selected, setSelected] = useState("");
  const [reviewTab, setReviewTab] = useState<"grade" | "assignment" | "tools">("grade");
  const [activeTool, setActiveTool] = useState<ReviewTool | null>(null);
  const [visitedTools, setVisitedTools] = useState<Set<ReviewTool>>(new Set());
  const [page, setPage] = useState(1); const [mobileTab, setMobileTab] = useState("document"); const [dirtyKeys, setDirtyKeys] = useState(new Set<string>());
  const [dirty, setDirty] = useState(false); const [advancedDirty, setAdvancedDirty] = useState(false); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true);
  const [error, setError] = useState(""); const [message, setMessage] = useState(""); const [assessmentError, setAssessmentError] = useState(false);
  const [dialog, setDialog] = useState<"publish" | "discard" | null>(null); const discardAction = useRef<() => void>(() => {});
  const writing = useRef(false);
  const requestedAssessment = useRef(""); const aiSending = useRef(false); const [aiBusy, setAiBusy] = useState(false);
  const [focusQuestion, setFocusQuestion] = useState("");
  const [focusCriterion,setFocusCriterion]=useState("");
  const [mappingTarget, setMappingTarget] = useState("");
  const [mappingDirty, setMappingDirty] = useState(false);
  const [highlight,setHighlight]=useState<EvidenceHighlight|null>(null);
  const [guideOpen,setGuideOpen]=useState(false);
  const evidenceRequest=useRef(0);
  const hasUnsaved = dirty || advancedDirty || mappingDirty;
  const unsavedRef = useRef(hasUnsaved); unsavedRef.current = hasUnsaved;
  const version = assessment?.items.find(v => v.id === selected);
  const criteria = data ? reviewCriteria(data, version) : [];
  const fetchData = useCallback(async () => {
    const [review, ai] = await Promise.all([platformRequest<ReviewResponse>(`/api/document-review/${submissionId}`), platformRequest<AssessmentResponse>(`/api/assessment/${submissionId}`).catch(() => null)]);
    return { review, ai };
  }, [submissionId]);
  function apply(review: ReviewResponse, ai: AssessmentResponse | null, id?: string) {
    const next = ai?.items.find(v => v.id === id) ?? ai?.items[0];
    setData(review); setAssessment(ai); setAssessmentError(ai === null); setSelected(next?.id ?? ""); setEditor(initialEditor(review, next)); setDirty(false); setDirtyKeys(new Set());
  }
  useEffect(() => { let active = true; setLoading(true); void fetchData().then(({ review, ai }) => { if (active) {
      apply(review, ai);
      const requestedQuestion = new URLSearchParams(window.location.search).get('question') ?? '';
      const validQuestion = review.questions.some(q => q.id === requestedQuestion);
      setFocusQuestion(validQuestion ? requestedQuestion : '');
      const cid=new URLSearchParams(window.location.search).get('criterion')??'';
      setFocusCriterion(review.questions.find(q=>q.id===requestedQuestion)?.criteria.some(c=>c.criterion_id===cid)?cid:'');
      const mappingRequested = validQuestion && new URLSearchParams(window.location.search).get('tool') === 'pages' && review.file_type === 'pdf';
      setMappingTarget(mappingRequested ? requestedQuestion : '');
      if(mappingRequested) { setReviewTab('tools'); setActiveTool('pages'); setVisitedTools(new Set(['pages'])); }
      setMobileTab(mappingRequested || new URLSearchParams(window.location.search).get('panel') === 'assessment' ? 'assessment' : 'document');
      const requestedPage = Number(new URLSearchParams(window.location.search).get('page'));
      setPage(Number.isSafeInteger(requestedPage) && requestedPage >= 1 && requestedPage <= (review.structure?.pages.length ?? 1) ? requestedPage : 1);
    } }).catch(() => { if (active) setError("Не удалось загрузить работу. Проверьте доступ и попробуйте снова."); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [fetchData]);
  useEffect(()=>{if(loading||!data)return;const query=new URLSearchParams(window.location.search);const q=query.get('question'),c=query.get('criterion');if(q&&c)document.getElementById(`review-criterion-${encodeURIComponent(q)}-${encodeURIComponent(c)}`)?.focus();},[loading,data?.submission_id]);
  const processingActive = assessment?.jobs.some(j => ['awaiting_source', 'queued', 'extracting', 'interpreting'].includes(j.status));
  const activeAssessmentId = assessment?.jobs.find(j => ['awaiting_source', 'queued', 'extracting', 'interpreting'].includes(j.status))?.id ?? '';
  useEffect(() => {
    if (!processingActive) return;
    let cancelled = false;
    const timer = window.setInterval(() => { void fetchData().then(r => {
      if (cancelled) return;
      const completed = r.ai?.items.find(v => v.job_id === (requestedAssessment.current || activeAssessmentId));
      const next = completed?.id ?? (selected || r.ai?.items[0]?.id);
      if (unsavedRef.current) {
        setAssessment(r.ai); setAssessmentError(r.ai === null);
        if (completed || !selected) setSelected(next ?? '');
      } else apply(r.review, r.ai, next);
      if (completed) { requestedAssessment.current = ''; setMessage('Баллы ИИ готовы и показаны рядом с критериями. Ваши изменения сохранены на экране.'); }
    }).catch(() => setMessage('Состояние обработки не обновилось. Сохранённая проверка остаётся доступна.')); }, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [processingActive, activeAssessmentId, hasUnsaved, fetchData, selected]);
  useEffect(() => {
    if (!hasUnsaved) return;
    const unload = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = ""; };
    const navigate = (e: MouseEvent) => {
      if (!unsavedRef.current) return;
      const logout = (e.target as HTMLElement).closest?.('.global-header button') as HTMLButtonElement | null;
      if (logout?.textContent?.trim() === 'Выйти') {
        e.preventDefault(); e.stopPropagation();
        discardAction.current = () => { unsavedRef.current = false; setDirty(false); setAdvancedDirty(false); logout.click(); };
        setDialog('discard'); return;
      }
      const link = (e.target as HTMLElement).closest?.('a[href]') as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || e.ctrlKey || e.metaKey || e.shiftKey || link.origin !== location.origin || link.href === location.href || link.hash) return;
      e.preventDefault(); e.stopPropagation(); discardAction.current = () => { unsavedRef.current = false; setDirty(false); setAdvancedDirty(false); router.push(link.href); }; setDialog("discard");
    };
    window.addEventListener("beforeunload", unload); document.addEventListener("click", navigate, true);
    return () => { window.removeEventListener("beforeunload", unload); document.removeEventListener("click", navigate, true); };
  }, [hasUnsaved, router]);
  const goToPage = useCallback((value: number) => { setPage(Math.max(1, Math.min(value, data?.structure?.pages.length ?? 1))); setMobileTab("document"); setMessage(`Открыта страница ${value}.`); }, [data?.structure?.pages.length]);
  function edit(key: string, patch: Partial<EditorValue>) { if (!editor) return; setEditor({ ...editor, criteria: { ...editor.criteria, [key]: { ...editor.criteria[key], ...patch } } }); setDirty(true); setDirtyKeys(keys => new Set([...keys, key])); setError(""); }
  function discardOr(action: () => void) { if (!hasUnsaved) { action(); return; } discardAction.current = action; setDialog("discard"); }
  function choose(id: string) { if (!data) return; const next = assessment?.items.find(v => v.id === id); if (!next) return; discardOr(() => { setSelected(id); setEditor(initialEditor(data, next)); setDirty(false); setDirtyKeys(new Set()); }); }
  function mode(next: ReviewEditor["mode"]) { if (!data || !editor || next === editor.mode) return; discardOr(() => { const values = initialEditor(data, next === 'assisted' ? version : undefined); setEditor({ ...values, mode: next }); setDirty(false); setDirtyKeys(new Set()); }); }
  async function refresh() { if (hasUnsaved) { setMessage("Сначала сохраните изменения, затем обновите предложения."); return; } try { const result = await fetchData(); if (unsavedRef.current) { setMessage('Данные обновились; введённые изменения сохранены на экране.'); return; } apply(result.review, result.ai, selected); setError(""); } catch { setError("Не удалось обновить данные. Введённые значения сохранены на экране."); } }
  async function showEvidence(criterion:CriterionView,index:number){
    const citation=criterion.suggestion?.evidence[index];if(!citation||!version)return;
    const ticket=++evidenceRequest.current;goToPage(citation.page_number);setHighlight({...citation,rectangles:[],loading:true});
    try{const result=await platformRequest<EvidenceHighlight>(`/api/document-review/${submissionId}/evidence-location`,{suggestion_id:version.id,question_id:criterion.question_id,criterion_id:criterion.criterion_id,evidence_index:index});if(ticket===evidenceRequest.current)setHighlight(result);}
    catch{if(ticket===evidenceRequest.current)setHighlight({...citation,rectangles:[],message:'Не удалось найти положение цитаты. Оригинал доступен для ручной проверки.'});}
  }
  async function assess(target?:CriterionView) {
    if (aiSending.current || processingActive || writing.current) return;
    aiSending.current = true; setAiBusy(true); setError("");
    try {
      const job = await platformRequest<{id: string; status: string}>(`/api/assessment/${submissionId}${!target&&assessment?.jobs[0]?.status === 'awaiting_budget' ? '/resume' : ''}`, !target&&assessment?.jobs[0]?.status === 'awaiting_budget' ? {} : { prepare: true, reanalyze: Boolean(version), ...(target&&version?{base_suggestion_id:version.id,target_criteria:[[target.question_id,target.criterion_id]]}:{}) });
      requestedAssessment.current = job.id;
      setAssessment(previous => previous ? {...previous, jobs: [{...job, error: ''}, ...previous.jobs.filter(j => j.id !== job.id)]} : {items: [], jobs: [{...job, error: ''}], supported: true});
      const result = await fetchData();
      const completed = result.ai?.items.find(v => v.job_id === job.id);
      setAssessment(result.ai); setAssessmentError(result.ai === null);
      if (completed) {
        if (unsavedRef.current) setSelected(completed.id);
        else apply(result.review, result.ai, completed.id);
        requestedAssessment.current = '';
      }
      setMessage(completed ? 'Сохранённые баллы ИИ показаны рядом с критериями.' : 'Проверка запущена. Баллы появятся рядом с критериями; можно продолжать работу.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Не удалось запустить проверку ИИ.'); }
    finally { aiSending.current = false; setAiBusy(false); }
  }
  async function save(asDraft: boolean) {
    if (!data || !editor || writing.current) return;
    const errors = editorErrors(criteria, editor); if (errors.length) { setError(errors[0]); return; }
    if (!asDraft && editor.mode === "manual" && !completeScores(criteria, editor)) { setError("Укажите балл по каждому критерию перед подтверждением. Неполную проверку можно сохранить как черновик."); return; }
    if (!asDraft && editor.mode === "assisted" && criteria.some(c => editor.criteria[c.key].action === "unreviewed")) { setError("По каждому критерию примите, отклоните или отложите предложение."); return; }
    writing.current = true; setBusy(true); setError(""); setMessage(""); let persisted = false;
    try {
      if (editor.mode === "assisted" && version) {
        await platformRequest(`/api/assessment/${submissionId}/decisions`, { suggestion_id: version.id, decisions: decisionsPayload(criteria, editor), draft: asDraft, feedback: editor.feedback });
      } else {
        await platformRequest(`/api/document-review/${submissionId}`, { criteria: manualPayload(criteria, editor), feedback: editor.feedback, draft: asDraft });
      }
      persisted = true;
      const result = await fetchData(); apply(result.review, result.ai, selected);
      setMessage(asDraft ? "Черновик сохранён. Официальная оценка не изменена." : "Решения сохранены. Публикация оценки выполняется отдельно.");
    } catch { setError(persisted ? "Проверка сохранена, но обновить экран не удалось. Обновите данные перед продолжением." : "Не удалось сохранить проверку. Введённые значения остались на экране; повторите попытку."); }
    finally { writing.current = false; setBusy(false); }
  }
  async function publish() {
    setDialog(null); if (!data || !editor || writing.current || hasUnsaved || !publicationReady(data, version, editor.mode)) return;
    writing.current = true; setBusy(true); setError("");
    try { await platformRequest(`/api/document-review/${submissionId}/publish`, { review_id: data.reviews[0].id, expected_published_review_id: data.published_grade?.review_id ?? null }); const result = await fetchData(); apply(result.review, result.ai, selected); setMessage("Оценка опубликована для студента."); }
    catch { setError("Не удалось подтвердить публикацию. Обновите данные и проверьте официальный статус перед повторной попыткой."); }
    finally { writing.current = false; setBusy(false); }
  }
  if (loading) return <div className="review-workspace-page"><div className="rw-loading" role="status"><span/> Загрузка работы и сохранённых решений…</div></div>;
  if (!data || !editor) return <div className="rw-empty" role="alert"><h1>Работа недоступна</h1><p>{error}</p><button className="rw-button" onClick={() => { setLoading(true); void fetchData().then(r => apply(r.review, r.ai)).catch(() => setError("Работа недоступна. Проверьте права доступа.")).finally(() => setLoading(false)); }}>Повторить загрузку</button></div>;
  const complete = completeScores(criteria, editor);
  const total = complete ? criteria.reduce((sum, c) => sum + Number(editor.criteria[c.key].points), 0) : null;

  const changedSincePublication = data.published_grade && data.reviews[0]?.id !== data.published_grade.review_id;
  const filled = criteria.filter(c => editor.criteria[c.key].points.trim() !== "").length;
  function openTool(tool: ReviewTool | null) { setActiveTool(tool); if(tool) setVisitedTools(previous => new Set([...previous, tool])); }
  const instruction = version?.rubric.spec.instructions || data.instructions || data.questions.map(q => q.statement).filter(Boolean).join("\n");
  return <div className="review-workspace-page rw-studio" data-mobile-panel={mobileTab}>
    <SubmissionOverview data={data}/>
    {error && <div className="rw-alert" role="alert"><span>{error}</span><button className="rw-text-button" disabled={hasUnsaved || busy} onClick={() => void refresh()}>Обновить данные</button></div>}
    {message && <div className="rw-notice" role="status">{message}</div>}
    {assessmentError && <div className="rw-notice">Предложения ИИ не загрузились. Ручная проверка доступна. <button className="rw-text-button" disabled={hasUnsaved} onClick={() => void refresh()}>Повторить загрузку</button></div>}
    <div className="rw-mobile-tabs" role="tablist" aria-label="Панели проверки" onKeyDown={e => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return; const next = e.key === 'Home' ? 0 : e.key === 'End' ? 1 : mobileTab === 'document' ? 1 : 0; setMobileTab(next ? 'assessment' : 'document'); e.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]')[next].focus(); e.preventDefault(); }}><button id="rw-tab-document" role="tab" aria-controls="rw-document-panel" tabIndex={mobileTab === 'document' ? 0 : -1} aria-selected={mobileTab === "document"} onClick={() => setMobileTab("document")}>Оригинал</button><button id="rw-tab-assessment" role="tab" aria-controls="rw-assessment-panel" tabIndex={mobileTab === 'assessment' ? 0 : -1} aria-selected={mobileTab === "assessment"} onClick={() => setMobileTab("assessment")}>Проверка <span>{criteria.length}</span></button></div>
    <div className="rw-workspace-grid"><div id="rw-document-panel" className="rw-document-column" role="tabpanel" aria-labelledby="rw-tab-document"><DocumentViewer submissionId={submissionId} fileName={data.file_name} fileType={data.file_type} pageCount={data.structure?.pages.length ?? 0} page={page} onPage={goToPage} highlight={highlight} onClearHighlight={()=>{evidenceRequest.current++;setHighlight(null);}}/></div>
      <section id="rw-assessment-panel" className="rw-assessment-panel" role="tabpanel" aria-labelledby="rw-tab-assessment">
        <div className="rw-studio-panel-heading"><div><h2>Проверка работы</h2><p>Баллы и комментарии для студента</p></div><span className="rw-fill-count"><strong>{filled} из {criteria.length}</strong><small>критериев</small></span></div>
        <div className="rw-completion-track" role="progressbar" aria-label="Заполнено критериев" aria-valuenow={filled} aria-valuemin={0} aria-valuemax={criteria.length}><span style={{width: `${criteria.length ? filled / criteria.length * 100 : 0}%`}}/></div>
        <div className="rw-studio-tabs" role="tablist" aria-label="Разделы проверки" onKeyDown={e => { const tabs = ['grade', 'assignment', 'tools'] as const; const index = tabs.indexOf(reviewTab); const next = e.key === 'ArrowRight' ? (index + 1) % 3 : e.key === 'ArrowLeft' ? (index + 2) % 3 : e.key === 'Home' ? 0 : e.key === 'End' ? 2 : -1; if(next < 0) return; e.preventDefault(); setReviewTab(tabs[next]); e.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]')[next].focus(); }}>
          {([['grade', 'Оценка'], ['assignment', 'Условия'], ['tools', 'Инструменты']] as const).map(([id, label]) => <button type="button" key={id} id={`review-tab-${id}`} role="tab" aria-selected={reviewTab === id} aria-controls={`review-view-${id}`} tabIndex={reviewTab === id ? 0 : -1} onClick={() => setReviewTab(id)}>{label}</button>)}
        </div>
        <div className="rw-assessment-scroll">
          <div id="review-view-grade" className="rw-studio-view" role="tabpanel" aria-labelledby="review-tab-grade" hidden={reviewTab !== 'grade'}>
            <section className={`rw-ai-summary ${version ? 'has-results' : ''}`} aria-label="Оценивание ИИ">
              <div><span className="rw-ai-eyebrow">Проверка по вашим критериям</span><h3>{criteria.length > 0 && criteria.every(c => c.suggestion?.proposed_score != null) ? `ИИ: ${scoreLabel(criteria.reduce((sum, c) => sum + (c.suggestion?.proposed_score ?? 0), 0),data.maximum_score)} / ${scoreLabel(data.maximum_score)}` : version ? `ИИ оценил ${criteria.filter(c => c.suggestion?.proposed_score != null).length} из ${criteria.length} критериев` : 'Получить оценку ИИ'}</h3><p>{processingActive ? 'Сначала читаем документ, затем оцениваем каждый критерий. Результат появится здесь.' : 'ИИ учитывает условия задания, приложенные файлы и максимальные баллы. Вы подтверждаете итог.'}</p></div>
              <button type="button" className="rw-button rw-primary" disabled={aiBusy || Boolean(processingActive) || busy || advancedDirty || !assessment?.supported} onClick={() => void assess()}>{aiBusy ? 'Запускаем…' : processingActive ? 'Проверяем…' : assessment?.jobs[0]?.status === 'awaiting_budget' ? 'Продолжить проверку' : assessment?.jobs[0]?.status === 'failed' ? 'Повторить проверку' : version ? 'Оценить заново' : 'Оценить по критериям'}</button>
              {assessment?.jobs[0]?.status === 'failed' && <p className="rw-field-error" role="status">{assessment.jobs[0].error_hint || 'Не удалось завершить оценивание. Повторите проверку; если ошибка повторится, откройте помощь ИИ.'}</p>}
              {assessment?.jobs[0]?.status === 'awaiting_budget' && <p className="rw-field-error" role="status">Проверка приостановлена из-за лимита бюджета. Продолжить можно, когда лимит позволит.</p>}
            </section>
            {version && <div className="rw-mode-choice"><span>Как оцениваем</span><div role="group" aria-label="Режим проверки"><button type="button" aria-pressed={editor.mode === 'manual'} disabled={busy || advancedDirty} onClick={() => mode('manual')}>Самостоятельно</button><button type="button" aria-pressed={editor.mode === 'assisted'} disabled={busy || advancedDirty} onClick={() => mode('assisted')}>С оценкой ИИ</button></div></div>}
            <RevisionContext submissionId={submissionId} criteria={criteria}/>
            {data.questions.length > 0 && <QuestionReviewNavigation data={data} question={focusQuestion} onQuestion={id=>{setFocusQuestion(id);setFocusCriterion('');}} criterion={focusCriterion} onCriterion={setFocusCriterion}/>}
            <RubricReviewPanel criteria={focusQuestion ? criteria.filter(c => c.question_id === focusQuestion&&(!focusCriterion||c.criterion_id===focusCriterion)) : criteria} editor={editor} onChange={edit} onPage={goToPage} busy={busy} dirtyKeys={dirtyKeys} savedState={editorSavedState(data, version, editor.mode)} onEvidence={(c,i)=>void showEvidence(c,i)} onRecheck={aiBusy||processingActive||busy||advancedDirty?undefined:c=>void assess(c)} comments={{submissionId,rubricId:version?.rubric.id}}/>
            <div className="rw-guide-entry"><button className="rw-text-button" disabled={busy||advancedDirty} aria-expanded={guideOpen} onClick={()=>setGuideOpen(v=>!v)}>{guideOpen?"Закрыть правила ИИ":"Настроить правила и примеры для ИИ"}</button>{guideOpen&&<TeachingGuide assignmentId={data.assignment_id} onDirty={setAdvancedDirty}/>}</div>
            <section className="rw-overall-feedback rw-feedback-visible"><label htmlFor="review-overall-feedback">Итоговый комментарий</label><p>Что студенту стоит учесть в следующей работе?</p><textarea id="review-overall-feedback" rows={3} maxLength={10000} value={editor.feedback} placeholder="Короткий отзыв о работе в целом…" disabled={busy} onChange={e => { setEditor({ ...editor, feedback: e.target.value }); setDirty(true); }}/><span className="rw-feedback-note">Студент увидит комментарии после публикации оценки.</span></section>
          </div>
          <div id="review-view-assignment" className="rw-studio-view rw-assignment-brief" role="tabpanel" aria-labelledby="review-tab-assignment" hidden={reviewTab !== 'assignment'}>
            <div className="rw-panel-intro"><h3>{data.title}</h3><p>Условия и критерии преподавателя</p></div>
            <section className="rw-tool-section"><h4>Что нужно выполнить</h4><p className="rw-assignment-text">{instruction || 'Автор задания не добавил описание.'}</p></section>
            <section className="rw-tool-section"><h4>Как распределяются баллы</h4>{criteria.map(c => <div className="rw-brief-criterion" key={c.key}><span>{c.description}</span><strong>{scoreLabel(c.maximum_points)}</strong></div>)}<div className="rw-brief-criterion rw-brief-total"><span>Максимум за работу</span><strong>{scoreLabel(data.maximum_score)}</strong></div></section>
            <button type="button" className="rw-button" onClick={() => setReviewTab('grade')}>Перейти к оценке</button>
          </div>
          <div id="review-view-tools" className="rw-studio-view" role="tabpanel" aria-labelledby="review-tab-tools" hidden={reviewTab !== 'tools'}>
            <ReviewToolsMenu tool={activeTool} onTool={openTool} fileType={data.file_type} submissionId={submissionId}>
              {visitedTools.has('pages') && <div hidden={activeTool !== 'pages'}><QuestionPages key={submissionId} embedded data={data} busy={busy} onPage={goToPage} onDirty={setMappingDirty} initialQuestionId={mappingTarget} reveal={!!mappingTarget}/></div>}
              {visitedTools.has('examples') && <div hidden={activeTool !== 'examples'}><DecisionMemory key={`${submissionId}/${selected}/${editor.mode}`} embedded data={data} rubricId={editor.mode === 'assisted' ? version?.rubric.id : undefined} criteria={criteria} editor={editor} busy={busy} onApply={edit}/></div>}
              {(['history', 'rubric', 'text', 'processing', 'student'] as const).filter(tool => visitedTools.has(tool)).map(tool => <div key={tool} hidden={activeTool !== tool}><AssessmentDiagnostics section={tool} submissionId={submissionId} data={data} assessment={assessment} selected={selected} onSelect={choose} dirty={hasUnsaved} onPage={goToPage} onAdvancedDirty={setAdvancedDirty} onRefresh={() => void refresh()}/></div>)}
            </ReviewToolsMenu>
          </div>
        </div>
      </section>
    </div>
    {changedSincePublication && <p className="rw-publication-note"><FileCheck size={14}/> Есть более новая сохранённая проверка. Студент пока видит ранее опубликованную оценку.</p>}
    {mappingDirty && <p className="rw-publication-note">Разметка страниц не сохранена. Откройте «Инструменты → Навигация по задачам» и сохраните изменения.</p>}
    {advancedDirty && <p className="rw-publication-note">Настройки критериев не сохранены. Завершите их в разделе «Инструменты → Настройки критериев».</p>}
    <ReviewActionBar savedState={editorSavedState(data, version, editor.mode)} dirty={hasUnsaved} busy={busy} hasSaved={!!(data.reviews.length || version?.decisions.length)} total={total} maximum={data.maximum_score} error={mappingDirty ? "Сначала сохраните страницы ответов в инструментах." : advancedDirty ? "Сначала сохраните настройки критериев в инструментах." : editorErrors(criteria, editor)[0] ?? null} onSave={() => void save(true)} onConfirm={() => void save(false)} onPublish={() => setDialog("publish")} publishable={publicationReady(data, version, editor.mode) && data.published_grade?.review_id !== data.reviews[0]?.id}/>
    {dialog === "publish" && <ReviewDialog title={data.published_grade ? "Обновить опубликованную оценку?" : "Опубликовать оценку?"} confirmLabel="Опубликовать для студента" onClose={() => setDialog(null)} onConfirm={() => void publish()}><p>Студент увидит последнюю сохранённую ручную проверку, её баллы и обратную связь.</p><p className="rw-publish-total">{scoreLabel(data.reviews[0]?.criteria.reduce((sum, c) => sum + (c.points ?? 0), 0),data.maximum_score)} / {scoreLabel(data.maximum_score)} <ArrowRight size={17}/> официальная оценка</p></ReviewDialog>}
    {dialog === "discard" && <ReviewDialog title="Есть несохранённые изменения" confirmLabel="Продолжить без сохранения" onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); discardAction.current(); }}><p>Сохраните изменения в проверке, рубрике и разметке страниц перед переходом.</p></ReviewDialog>}
  </div>;
}
