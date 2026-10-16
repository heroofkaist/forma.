"use client";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, BookOpen, Clock3, FileSearch, FileText, LayoutGrid, Settings2, Sparkles, Users } from "lucide-react";

export const reviewTools = [
  { id: "history", title: "История проверки", description: "Сохранённые оценки, черновики и версии предложений ИИ.", icon: Clock3 },
  { id: "pages", title: "Страницы ответов", description: "Отметьте, на каких страницах решён каждый вопрос.", icon: LayoutGrid },
  { id: "examples", title: "Примеры комментариев", description: "Используйте объяснения из прошлых проверок этого курса.", icon: BookOpen },
  { id: "rubric", title: "Настройки критериев", description: "Уточните инструкции и требования для проверки.", icon: Settings2 },
  { id: "text", title: "Текст работы", description: "Просмотрите извлечённый текст и предупреждения.", icon: FileText },
  { id: "processing", title: "Помощь ИИ", description: "Распознавание документа и повторный анализ по запросу.", icon: Sparkles },
  { id: "student", title: "История студента", description: "Подтверждённые наблюдения по другим работам курса.", icon: Users },
] as const;
export type ReviewTool = typeof reviewTools[number]["id"];
export function ReviewToolsMenu({ tool, onTool, fileType, submissionId, children }: { tool: ReviewTool | null; onTool: (value: ReviewTool | null) => void; fileType: string; submissionId: string; children: React.ReactNode }) {
  const selected = reviewTools.find(item => item.id === tool);
  return <div className="rw-tools-home">
    {selected ? <header className="rw-tool-header"><button type="button" className="rw-text-button" onClick={() => onTool(null)}><ArrowLeft size={15}/> Все инструменты</button><h3>{selected.title}</h3><p>{selected.description}</p></header> : <><div className="rw-panel-intro"><h3>Инструменты проверки</h3><p>Откройте нужный инструмент. Баллы и комментарии останутся на вкладке «Оценка».</p></div><div className="rw-tool-cards">{reviewTools.filter(item => item.id !== 'pages' || fileType === 'pdf').map(item => <button className="rw-tool-card" type="button" key={item.id} onClick={() => onTool(item.id)}><item.icon size={19} aria-hidden="true"/><span><strong>{item.title}</strong><small>{item.description}</small></span><ArrowUpRight size={16} aria-hidden="true"/></button>)}<Link className="rw-tool-card" href={`/teacher/submissions/${submissionId}/originality`}><FileSearch size={19}/><span><strong>Сходство с другими работами</strong><small>Откройте отчёт о совпадениях и его источники.</small></span><ArrowUpRight size={16}/></Link></div></>}
    {children}
  </div>;
}
