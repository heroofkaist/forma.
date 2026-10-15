"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, FileCheck } from "lucide-react";
import { platformRequest } from "../../lib/platform";
import { publicationReady, completeScores, editorErrors, initialEditor, manualPayload, reviewCriteria, decisionsPayload } from "../../lib/review-workspace";
import type { AssessmentResponse, EditorValue, ReviewEditor, ReviewResponse } from "../../lib/review-workspace";
import { RubricReviewPanel } from "../assessment-panel";
import { DocumentViewer } from "./document-viewer";
import { SubmissionOverview } from "./submission-overview";
import { ReviewActionBar } from "./review-action-bar";
import { AssessmentDiagnostics } from "./assessment-diagnostics";

function ReviewDialog({ title, children, onClose, onConfirm, confirmLabel }: { title: string; children: React.ReactNode; onClose: () => void; onConfirm: () => void; confirmLabel: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current!; const previous = document.activeElement as HTMLElement | null; dialog.showModal(); return () => { dialog.close(); previous?.focus(); }; }, []);
  return <dialog ref={ref} className="rw-dialog" aria-labelledby="review-dialog-title" onCancel={e => { e.preventDefault(); onClose(); }}><h2 id="review-dialog-title">{title}</h2>{children}<div className="rw-dialog-actions"><button className="rw-button" onClick={onClose} autoFocus>Отмена</button><button className="rw-button rw-primary" onClick={onConfirm}>{confirmLabel}</button></div></dialog>;
}
export function TeacherReviewWorkspace({ submissionId }: { submissionId: string }) {
  const router = useRouter(); const [data, setData] = useState<ReviewResponse | null>(null); const [assessment, setAssessment] = useState<AssessmentResponse | null>(null);
  const [editor, setEditor] = useState<ReviewEditor | null>(null); const [selected, setSelected] = useState(""); const [expanded, setExpanded] = useState<string | null>(null);
  const [page, setPage] = useState(1); const [mobileTab, setMobileTab] = useState("document"); const [dirtyKeys, setDirtyKeys] = useState(new Set<string>());
  const [dirty, setDirty] = useState(false); const [advancedDirty, setAdvancedDirty] = useState(false); const [busy, setBusy] = useState(false); const [loading, setLoading] = useState(true);
  const [error, setError] = useState(""); const [message, setMessage] = useState(""); const [assessmentError, setAssessmentError] = useState(false);
  const [dialog, setDialog] = useState<"publish" | "discard" | null>(null); const discardAction = useRef<() => void>(() => {});
  const hasUnsaved = dirty || advancedDirty;
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
  useEffect(() => { let active = true; setLoading(true); void fetchData().then(({ review, ai }) => { if (active) apply(review, ai); }).catch(() => { if (active) setError("Не удалось загрузить работу. Проверьте доступ и попробуйте снова."); }).finally(() => { if (active) setLoading(false); }); return () => { active = false; }; }, [fetchData]);
  const processingActive = assessment?.jobs.some(j => ['queued', 'extracting', 'interpreting'].includes(j.status));
  useEffect(() => {
    if (!processingActive || hasUnsaved) return;
    let cancelled = false;
    const timer = window.setInterval(() => { void fetchData().then(r => {
      if (cancelled || unsavedRef.current) return;
      apply(r.review, r.ai, selected);
      if (selected && r.ai?.items[0] && r.ai.items[0].id !== selected) setMessage('Новая версия предложений доступна в истории проверок.');
    }).catch(() => setMessage('Состояние обработки не обновилось. Сохранённая проверка остаётся доступна.')); }, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [processingActive, hasUnsaved, fetchData, selected]);
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
  function choose(id: string) { if (!data) return; const next = assessment?.items.find(v => v.id === id); if (!next) return; discardOr(() => { setSelected(id); setEditor(initialEditor(data, next)); setDirty(false); setDirtyKeys(new Set()); setExpanded(null); }); }
  function mode(next: ReviewEditor["mode"]) { if (!data || !editor || next === editor.mode) return; discardOr(() => { const values = initialEditor(data, next === 'assisted' ? version : undefined); setEditor({ ...values, mode: next }); setDirty(false); setDirtyKeys(new Set()); }); }
  async function refresh() { if (hasUnsaved) { setMessage("Сначала сохраните изменения, затем обновите предложения."); return; } try { const result = await fetchData(); if (unsavedRef.current) { setMessage('Данные обновились; введённые изменения сохранены на экране.'); return; } apply(result.review, result.ai, selected); setError(""); } catch { setError("Не удалось обновить данные. Введённые значения сохранены на экране."); } }
  async function save(asDraft: boolean) {
    if (!data || !editor) return;
    const errors = editorErrors(criteria, editor); if (errors.length) { setError(errors[0]); return; }
    if (!asDraft && editor.mode === "manual" && !completeScores(criteria, editor)) { setError("Укажите балл по каждому критерию перед подтверждением. Неполную проверку можно сохранить как черновик."); return; }
    if (!asDraft && editor.mode === "assisted" && criteria.some(c => editor.criteria[c.key].action === "unreviewed")) { setError("По каждому критерию примите, отклоните или отложите предложение."); return; }
    setBusy(true); setError(""); setMessage(""); let persisted = false;
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
    finally { setBusy(false); }
  }
  async function publish() {
    setDialog(null); if (!data || !editor || hasUnsaved || !publicationReady(data, version, editor.mode)) return;
    setBusy(true); setError("");
    try { await platformRequest(`/api/document-review/${submissionId}/publish`, { review_id: data.reviews[0].id, expected_published_review_id: data.published_grade?.review_id ?? null }); const result = await fetchData(); apply(result.review, result.ai, selected); setMessage("Оценка опубликована для студента."); }
    catch { setError("Не удалось подтвердить публикацию. Обновите данные и проверьте официальный статус перед повторной попыткой."); }
    finally { setBusy(false); }
  }
  if (loading) return <div className="review-workspace-page"><div className="rw-loading" role="status"><span/> Загрузка работы и сохранённых решений…</div></div>;
  if (!data || !editor) return <div className="rw-empty" role="alert"><h1>Работа недоступна</h1><p>{error}</p><button className="rw-button" onClick={() => { setLoading(true); void fetchData().then(r => apply(r.review, r.ai)).catch(() => setError("Работа недоступна. Проверьте права доступа.")).finally(() => setLoading(false)); }}>Повторить загрузку</button></div>;
  const complete = completeScores(criteria, editor);
  const total = complete ? criteria.reduce((sum, c) => sum + Number(editor.criteria[c.key].points), 0) : null;
  const reviewed = criteria.filter(c => editor.mode === "manual" ? data.reviews[0]?.criteria.some(s => s.question_id === c.question_id && s.criterion_id === c.criterion_id && s.points !== null && s.confirmed !== false) : c.saved?.confirmed !== false && ['accepted', 'rejected'].includes(c.saved?.action ?? '')).length;
  const changedSincePublication = data.published_grade && data.reviews[0]?.id !== data.published_grade.review_id;
  return <div className="review-workspace-page" data-mobile-panel={mobileTab}>
    <SubmissionOverview data={data} aiAvailable={!!version} reviewed={reviewed} total={criteria.length}/>
    {error && <div className="rw-alert" role="alert"><span>{error}</span><button className="rw-text-button" disabled={hasUnsaved || busy} onClick={() => void refresh()}>Обновить данные</button></div>}
    {message && <div className="rw-notice" role="status">{message}</div>}
    {assessmentError && <div className="rw-notice">Предложения ИИ не загрузились. Ручная проверка доступна. <button className="rw-text-button" disabled={hasUnsaved} onClick={() => void refresh()}>Повторить загрузку</button></div>}
    <div className="rw-mobile-tabs" role="tablist" aria-label="Панели проверки" onKeyDown={e => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return; const next = e.key === 'Home' ? 0 : e.key === 'End' ? 1 : mobileTab === 'document' ? 1 : 0; setMobileTab(next ? 'assessment' : 'document'); e.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]')[next].focus(); e.preventDefault(); }}><button id="rw-tab-document" role="tab" aria-controls="rw-document-panel" tabIndex={mobileTab === 'document' ? 0 : -1} aria-selected={mobileTab === "document"} onClick={() => setMobileTab("document")}>Оригинал</button><button id="rw-tab-assessment" role="tab" aria-controls="rw-assessment-panel" tabIndex={mobileTab === 'assessment' ? 0 : -1} aria-selected={mobileTab === "assessment"} onClick={() => setMobileTab("assessment")}>Критерии <span>{criteria.length}</span></button></div>
    <div className="rw-workspace-grid"><div id="rw-document-panel" className="rw-document-column" role="tabpanel" aria-labelledby="rw-tab-document"><DocumentViewer submissionId={submissionId} fileName={data.file_name} fileType={data.file_type} pageCount={data.structure?.pages.length ?? 0} page={page} onPage={goToPage}/></div>
      <section id="rw-assessment-panel" className="rw-assessment-panel" role="tabpanel" aria-labelledby="rw-tab-assessment"><div className="rw-panel-heading"><div><h2>Критерии оценки</h2><p>Решение остаётся за преподавателем</p></div><span className="rw-count">{criteria.length}</span></div>
        <div className="rw-mode-toggle" role="group" aria-label="Режим проверки"><button aria-pressed={editor.mode === "assisted"} disabled={!version || busy || advancedDirty} onClick={() => mode("assisted")}>С предложениями ИИ</button><button aria-pressed={editor.mode === "manual"} disabled={busy || advancedDirty} onClick={() => mode("manual")}>Вручную</button></div>
        <div className="rw-assessment-scroll"><div className="rw-rubric-intro"><details><summary>Требования задания</summary><p>{version?.rubric.spec.instructions || data.instructions || data.questions.map(q => q.statement).filter(Boolean).join('\n') || "Полные инструкции не указаны. Уточните их у автора задания."}</p></details>
          {!version && <p className="rw-muted">Сохранённых предложений нет. Работу можно оценить вручную без запуска модели.</p>}
          {version && <div className="rw-ai-overview"><span>ИИ: {criteria.filter(c => c.suggestion?.finding === 'strength').length} сильных сторон</span><span>{criteria.filter(c => ['concern', 'mixed'].includes(c.suggestion?.finding ?? '')).length} замечаний</span><span>{criteria.filter(c => c.suggestion?.proposed_score == null).length} без балла</span></div>}
        </div>
        <RubricReviewPanel criteria={criteria} editor={editor} expanded={expanded} onExpand={setExpanded} onChange={edit} onPage={goToPage} busy={busy} dirtyKeys={dirtyKeys}/>
        <details className="rw-overall-feedback"><summary>Общая обратная связь <span>{editor.feedback ? 'есть комментарий' : 'для студента'}</span></summary><label className="rw-sr-only" htmlFor="review-overall-feedback">Общая обратная связь</label><textarea id="review-overall-feedback" rows={4} maxLength={10000} value={editor.feedback} placeholder="Итоговый комментарий к работе…" disabled={busy} onChange={e => { setEditor({ ...editor, feedback: e.target.value }); setDirty(true); }}/><p className="rw-muted">Студент увидит подтверждённую обратную связь после публикации.</p></details>
        <AssessmentDiagnostics submissionId={submissionId} data={data} assessment={assessment} selected={selected} onSelect={choose} dirty={hasUnsaved} onPage={goToPage} onAdvancedDirty={setAdvancedDirty} onRefresh={() => void refresh()}/>
        </div>
      </section>
    </div>
    {changedSincePublication && <p className="rw-publication-note"><FileCheck size={14}/> Есть более новая сохранённая проверка. Студент пока видит ранее опубликованную оценку.</p>}
    {advancedDirty && <p className="rw-publication-note">Сохраните изменения расширенной рубрики в её настройках.</p>}
    <ReviewActionBar dirty={hasUnsaved} busy={busy} hasSaved={!!(data.reviews.length || version?.decisions.length)} total={total} maximum={data.maximum_score} error={editorErrors(criteria, editor)[0] ?? null} onSave={() => void save(true)} onConfirm={() => void save(false)} onPublish={() => setDialog("publish")} publishable={publicationReady(data, version, editor.mode) && data.published_grade?.review_id !== data.reviews[0]?.id}/>
    {dialog === "publish" && <ReviewDialog title={data.published_grade ? "Обновить опубликованную оценку?" : "Опубликовать оценку?"} confirmLabel="Опубликовать для студента" onClose={() => setDialog(null)} onConfirm={() => void publish()}><p>Студент увидит последнюю сохранённую ручную проверку, её баллы и обратную связь.</p><p className="rw-publish-total">{data.reviews[0]?.criteria.reduce((sum, c) => sum + (c.points ?? 0), 0)} / {data.maximum_score} <ArrowRight size={17}/> официальная оценка</p></ReviewDialog>}
    {dialog === "discard" && <ReviewDialog title="Есть несохранённые изменения" confirmLabel="Продолжить без сохранения" onClose={() => setDialog(null)} onConfirm={() => { setDialog(null); discardAction.current(); }}><p>Сохраните проверку, чтобы не потерять введённые баллы и комментарии.</p></ReviewDialog>}
  </div>;
}
