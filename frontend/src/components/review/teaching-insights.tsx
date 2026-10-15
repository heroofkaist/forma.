"use client";
import { useState } from "react";
import Link from "next/link";
import { platformRequest } from "../../lib/platform";
import { categoryLabels } from "../../lib/review-workspace";
import { loadTeachingInsights, type InsightsState, type TeachingInsightsResponse } from "../../lib/teaching-insights";

export function TeachingInsightsContent({state}: {state: InsightsState}) {
  if (state.status === "idle") return <p>Загрузите сохранённые наблюдения по этому студенту в этом курсе.</p>;
  if (state.status === "loading") return <p role="status">Загружаем подтверждённые наблюдения…</p>;
  if (state.status === "error") return <p role="alert">Не удалось загрузить наблюдения. Попробуйте снова.</p>;
  return <>
    <p className="rw-muted">История этого студента в этом курсе. Для каждой категории и метки считаются отдельные работы с принятым и подтверждённым решением преподавателя. Учитывается последнее подтверждённое решение по каждой категории и метке; черновики и предложения ИИ без подтверждения не учитываются. Одна работа считается один раз для каждой метки.</p>
    {!state.data?.items.length ? <p className="rw-empty">Подтверждённых наблюдений пока нет. Они появятся после принятия решений по критериям с метками истории.</p> : state.data.items.map(item => <section className="rw-detail" key={`${item.category}/${item.tag}`}>
      <h3>{categoryLabels[item.category] ?? item.category} · {item.tag}</h3>
      <p>Работ с замечаниями: <strong>{item.confirmed_concerns}</strong> из <strong>{item.reviewed_submissions}</strong> проверенных по этой метке.</p>
      <details><summary>Основания преподавательских наблюдений</summary>{item.evidence.length ? item.evidence.map(e => <div className="rw-history-row" key={`${e.decision_id}/${e.criterion_id}`}>
        <Link className="rw-text-button" href={`/teacher/submissions/${encodeURIComponent(e.submission_id)}/review`}>Открыть проверенную работу →</Link>
        {e.source.map((source, i) => <blockquote key={i}><Link href={`/teacher/submissions/${encodeURIComponent(e.submission_id)}/review?page=${source.page_number}`}>Страница {source.page_number}</Link><p>{source.quote}</p></blockquote>)}
        {!e.source.length && <p>Текстовый фрагмент не сохранён; основание доступно в проверке работы.</p>}
      </div>) : <p>По этой метке подтверждены решения без замечаний.</p>}</details>
    </section>)}
  </>;
}
export function TeachingInsights({submissionId}: {submissionId: string}) {
  const [state, setState] = useState<InsightsState>({status: "idle", data: null});
  return <div aria-busy={state.status === "loading"}><button className="rw-button" disabled={state.status === "loading"} onClick={() => void loadTeachingInsights(() => platformRequest<TeachingInsightsResponse>(`/api/assessment/${submissionId}/insights`), setState)}>{state.status === "error" ? "Повторить загрузку" : state.status === "loaded" ? "Обновить историю" : "Загрузить историю"}</button><TeachingInsightsContent state={state}/></div>;
}
