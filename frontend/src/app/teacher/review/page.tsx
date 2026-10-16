"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { ClipboardCheck, Search, ArrowRight } from "lucide-react";
import { AppShell } from "../../../components/app-shell";
import { platformRequest } from "../../../lib/platform";
type Item = { id: string; assignment_title: string; student_name: string; submitted_at: string };
export default function ReviewQueue() {
  const [items, setItems] = useState<Item[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState(""), [query, setQuery] = useState("");
  async function load() { setLoading(true); setError(""); try { const data = await platformRequest<{ review_queue: Item[] }>("/api/teacher-overview"); setItems(data.review_queue); } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить очередь. Попробуйте ещё раз."); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  const visible = items.filter(item => `${item.student_name} ${item.assignment_title}`.toLocaleLowerCase("ru").includes(query.trim().toLocaleLowerCase("ru")));
  return <AppShell><section className="academic-heading"><div><div className="eyebrow">ПРОВЕРКА И ОБРАТНАЯ СВЯЗЬ</div><h1>Очередь проверки</h1><p>Работы ваших курсов, для которых оценка ещё не опубликована.</p></div>{!loading && !error && <span className="queue-count">В очереди: {items.length}</span>}</section>
    {error && <div className="notice error-notice" role="alert">{error}<button className="button" onClick={() => void load()}>Повторить загрузку</button></div>}
    {loading ? <p className="student-loading" role="status">Загружаем очередь…</p> : !error && <><div className="course-collection-heading"><p className="queue-filter-count" role="status">Показано: {visible.length} из {items.length}</p><label className="course-search"><Search size={18} aria-hidden="true"/><input type="search" aria-label="Поиск в очереди проверки" placeholder="Студент или задание" value={query} onChange={e => setQuery(e.target.value)}/></label></div>{visible.length ? <div className="student-table-wrap"><table className="student-table review-queue-table"><thead><tr><th scope="col">СТУДЕНТ</th><th scope="col">ЗАДАНИЕ</th><th scope="col">ОТПРАВЛЕНО</th><th scope="col"><span className="rw-sr-only">Действия</span></th></tr></thead><tbody>{visible.map(item => <tr key={item.id}><td data-label="Студент"><strong>{item.student_name}</strong></td><td data-label="Задание">{item.assignment_title}</td><td data-label="Отправлено">{Number.isFinite(Date.parse(item.submitted_at)) ? new Date(item.submitted_at).toLocaleDateString("ru-RU") : "Дата не указана"}</td><td data-label="Действия"><Link className="button" href={`/teacher/submissions/${item.id}/review`}>Проверить<ArrowRight size={16} aria-hidden="true"/></Link></td></tr>)}</tbody></table></div> : <div className="student-empty"><ClipboardCheck size={30} aria-hidden="true"/><h2>{query ? "Работы не найдены" : "Сейчас проверять нечего"}</h2><p>{query ? "Попробуйте другое имя студента или название задания." : "Новые работы появятся здесь после отправки студентами."}</p>{query ? <button className="button" onClick={() => setQuery("")}>Сбросить поиск</button> : <Link className="button" href="/teacher">Открыть мои курсы</Link>}</div>}</>}
  </AppShell>;
}
