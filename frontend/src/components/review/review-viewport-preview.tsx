"use client";
import { useState } from "react";
/** Development-only harness: exact CSS viewports without changing browser settings. */
export function ReviewViewportPreview({ submissionId }: { submissionId: string }) {
  const [width, setWidth] = useState(1440);
  return <main style={{ padding: 16 }}><div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}><strong>Просмотр интерфейса · сохранённые данные</strong><button className="rw-button" aria-pressed={width === 1440} onClick={() => setWidth(1440)}>1440 × 900</button><button className="rw-button" aria-pressed={width === 390} onClick={() => setWidth(390)}>390 × 900</button><span style={{fontSize: 12, color: '#747e78'}}>Модели не запускаются автоматически.</span></div><div style={{overflow: 'auto'}}><iframe title={`Проверка работы · ${width} пикселей`} src={`/teacher/submissions/${encodeURIComponent(submissionId)}/review`} width={width} height={900} style={{ width, height:900, maxWidth:'none', display:'block', margin:'0 auto', border:'1px solid #dce2dc', boxSizing:'content-box', background:'#f7f8f6' }}/></div></main>;
}
