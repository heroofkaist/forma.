"use client";

import { useState } from "react";
import { Check, FileText, Sparkles, ArrowRight, Eye } from "lucide-react";

const stages = [
  { title: "Откройте работу", body: "Оригинал документа и критерии находятся рядом. Условия задания доступны во время проверки." },
  { title: "Проверьте баллы ИИ", body: "У каждого критерия — предложенный балл, обоснование и фрагменты работы. Любой балл можно изменить." },
  { title: "Дайте обратную связь", body: "Сохраните проверку и опубликуйте результат, когда будете готовы. До публикации студент его не увидит." },
];

/** An explicitly labelled, static teaching example. Never invokes an AI provider. */
export function ProductTour({ compact = false }: { compact?: boolean }) {
  const [stage, setStage] = useState(1);
  return <div className={`product-tour${compact ? " is-compact" : ""}`}>
    <div className="tour-top"><span className="tour-window-dots" aria-hidden="true"><i/><i/><i/></span><span>Пример проверки · вымышленные данные</span><span className="tour-private"><Eye size={13} aria-hidden="true"/>Только преподавателю</span></div>
    <div className="tour-context"><div><span>Физика · Законы движения</span><strong>Работа Анны</strong></div><span className="tour-draft">{stage === 2 ? "Проверка сохранена" : "Черновик проверки"}</span></div>
    <div className="tour-workspace">
      <div className={`tour-document${stage === 0 ? " is-emphasized" : ""}`}><div className="tour-document-label"><FileText size={14} aria-hidden="true"/>Оригинал · страница 1</div><article><span className="tour-paper-kicker">Задача 1</span><h3>Сила и ускорение</h3><p>На тело массой 2 кг действует сила 6 Н. Найдите ускорение.</p><div className="tour-equation">F = ma<br/><mark>a = F / m = 3 м/с²</mark></div><p className="tour-paper-answer">Ускорение направлено вдоль действующей силы.</p><span className="tour-page-number">1</span></article></div>
      <div className="tour-grading"><div className="tour-grading-title"><Sparkles size={16} aria-hidden="true"/><strong>Оценка по критериям</strong></div><section className={`tour-rubric${stage === 1 ? " is-emphasized" : ""}`}><div><span>Применение закона</span><span className="tour-score">10 <small>/ 10</small></span></div><span className="tour-ai-label">Предложение ИИ</span><p>Верно выбрана формула и подставлены значения.</p><span className="tour-citation">Основание: страница 1</span></section><section className="tour-rubric"><div><span>Ответ и единицы</span><span className="tour-score">10 <small>/ 10</small></span></div><span className="tour-ai-label">Предложение ИИ</span><p>Ответ 3 м/с² соответствует условию.</p></section><div className={`tour-confirmation${stage === 2 ? " is-complete" : ""}`}><Check size={17} aria-hidden="true"/><span>{stage === 2 ? "Преподаватель подтвердил 20 / 20" : "Каждый балл подтверждаете вы"}</span></div></div>
    </div>
    {!compact && <><div className="tour-steps" role="group" aria-label="Посмотреть этап проверки">{stages.map((item, i) => <button type="button" key={item.title} aria-pressed={stage === i} onClick={() => setStage(i)}><span>{i + 1}</span>{item.title}<ArrowRight size={15} aria-hidden="true"/></button>)}</div><p className="tour-description" aria-live="polite">{stages[stage].body}</p></>}
  </div>;
}
