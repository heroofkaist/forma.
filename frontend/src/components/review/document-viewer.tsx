"use client";
import { memo, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Expand, Minus, Plus, RotateCcw, X } from "lucide-react";
import { authenticatedResourceUrl, downloadAuthenticatedFile } from "../../lib/api";

type Props = { submissionId: string; fileName: string; fileType: string; pageCount: number; page: number; onPage: (page: number) => void };
export const DocumentViewer = memo(function DocumentViewer({ submissionId, fileName, fileType, pageCount, page, onPage }: Props) {
  const [source, setSource] = useState(""); const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  const [zoom, setZoom] = useState(100); const [expanded, setExpanded] = useState(false); const [retry, setRetry] = useState(0);
  const cache = useRef(new Map<number, string>()); const panel = useRef<HTMLElement>(null); const expandButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const urls = cache.current;
    return () => { urls.forEach(url => URL.revokeObjectURL(url)); urls.clear(); };
  }, [submissionId]);
  useEffect(() => {
    if (fileType !== "pdf" || !pageCount) return;
    let active = true; setError(""); setLoading(true);
    const found = cache.current.get(page);
    if (found) { setSource(found); setLoading(false); return; }
    void authenticatedResourceUrl(`/api/document-review/${submissionId}/pages/${page}`).then(url => {
      if (!active) { URL.revokeObjectURL(url); return; }
      cache.current.set(page, url);
      while (cache.current.size > 5) { const first = cache.current.keys().next().value as number; URL.revokeObjectURL(cache.current.get(first)!); cache.current.delete(first); }
      setSource(url); setLoading(false);
    }).catch(() => { if (active) { setLoading(false); setError("Не удалось открыть страницу. Повторите загрузку или скачайте оригинал."); } });
    return () => { active = false; };
  }, [submissionId, fileType, page, pageCount, retry]);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.body.style.overflow; document.body.style.overflow = "hidden";
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setExpanded(false); expandButton.current?.focus(); }
      if (event.key === "Tab") {
        const focusable = panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), select:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]');
        if (!focusable?.length) return;
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) { last.focus(); event.preventDefault(); }
        else if (!event.shiftKey && document.activeElement === last) { first.focus(); event.preventDefault(); }
      }
    };
    document.addEventListener("keydown", keydown); expandButton.current?.focus();
    return () => { document.body.style.overflow = previous; document.removeEventListener("keydown", keydown); };
  }, [expanded]);
  async function download() { try { await downloadAuthenticatedFile(`/api/submission-files/${submissionId}`, fileName); } catch { setError("Не удалось скачать оригинал. Повторите попытку."); } }
  return <section ref={panel} className={`rw-document ${expanded ? "rw-document-expanded" : ""}`} aria-label="Оригинал работы" role={expanded ? "dialog" : undefined} aria-modal={expanded || undefined}>
    <div className="rw-document-toolbar"><div className="rw-page-controls"><button className="rw-icon-button" aria-label="Предыдущая страница" disabled={page <= 1 || loading} onClick={() => onPage(page - 1)}><ChevronLeft size={17}/></button>
      <label className="rw-page-label"><span className="rw-sr-only">Страница</span><select aria-label="Страница" value={page} disabled={!pageCount} onChange={e => onPage(Number(e.target.value))}>{Array.from({ length: pageCount }, (_, i) => <option key={i} value={i + 1}>{i + 1}</option>)}</select><span>из {pageCount || "—"}</span></label>
      <button className="rw-icon-button" aria-label="Следующая страница" disabled={page >= pageCount || loading} onClick={() => onPage(page + 1)}><ChevronRight size={17}/></button></div>
      <div className="rw-zoom-controls"><button className="rw-icon-button" aria-label="Уменьшить масштаб" disabled={zoom <= 75} onClick={() => setZoom(v => v - 25)}><Minus size={15}/></button><button className="rw-zoom-value" aria-label="По ширине страницы" onClick={() => setZoom(100)}>{zoom === 100 ? "По ширине" : `${zoom}%`}</button><button className="rw-icon-button" aria-label="Увеличить масштаб" disabled={zoom >= 200} onClick={() => setZoom(v => v + 25)}><Plus size={15}/></button></div>
      <div className="rw-document-actions"><button className="rw-icon-button" aria-label="Скачать оригинал" title="Скачать оригинал" onClick={() => void download()}><Download size={16}/></button><button ref={expandButton} className="rw-icon-button" aria-label={expanded ? "Закрыть полноэкранный документ" : "Развернуть документ"} aria-expanded={expanded} onClick={() => setExpanded(v => !v)}>{expanded ? <X size={17}/> : <Expand size={16}/>}</button></div>
    </div>
    <div className="rw-document-stage" aria-busy={loading} tabIndex={0} aria-label="Область документа, прокрутка" onKeyDown={e => { if ((e.target as HTMLElement).tagName !== "DIV") return; if (e.key === "ArrowRight" && page < pageCount) { onPage(page + 1); e.preventDefault(); } if (e.key === "ArrowLeft" && page > 1) { onPage(page - 1); e.preventDefault(); } }}>
      {fileType !== "pdf" ? <div className="rw-viewer-state"><strong>Предпросмотр этого формата недоступен</strong><p>Скачайте оригинал для проверки. Извлечённый текст доступен в диагностике.</p><button className="rw-button" onClick={() => void download()}>Скачать оригинал</button></div> : error ? <div className="rw-viewer-state" role="alert"><p>{error}</p><button className="rw-button" onClick={() => setRetry(v => v + 1)}><RotateCcw size={14}/> Повторить</button></div> : loading ? <div className="rw-paper-skeleton" role="status">Загрузка страницы…</div> : source ? <img className="rw-page-image" src={source} width={1131} height={1600} alt={`Оригинал работы, страница ${page} из ${pageCount}`} style={{ width: `${zoom}%` }} onError={() => setError("Не удалось показать страницу. Попробуйте загрузить её снова.")}/> : <div className="rw-viewer-state">Страницы пока недоступны. Оригинал можно скачать.</div>}
    </div>
    <div className="rw-document-caption"><span>{fileName}</span><span>Оригинал · стр. {page}</span></div>
  </section>;
});
