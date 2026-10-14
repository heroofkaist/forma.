"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {AppShell} from '../../../components/app-shell';
import {platformRequest} from '../../../lib/platform';
type Item={id:string;assignment_title:string;student_name:string;submitted_at:string};
export default function ReviewQueue(){
 const [items,setItems]=useState<Item[]>([]);const [loading,setLoading]=useState(true);const [error,setError]=useState('');
 useEffect(()=>{platformRequest<{review_queue:Item[]}>('/api/teacher-overview').then((data)=>setItems(data.review_queue)).catch((cause:unknown)=>setError(cause instanceof Error?cause.message:'Не удалось загрузить очередь.')).finally(()=>setLoading(false));},[]);
 return <AppShell><section className="academic-heading"><div><h1>Очередь проверки</h1><p>Работы доступных вам курсов, для которых оценка ещё не опубликована.</p></div></section>{error&&<div className="notice error-notice" role="alert">{error}</div>}{loading?<p>Загрузка…</p>:items.length?<div className="student-table-wrap"><table className="student-table"><thead><tr><th>ЗАДАНИЕ</th><th>СТУДЕНТ</th><th>ОТПРАВЛЕНО</th><th></th></tr></thead><tbody>{items.map((item)=><tr key={item.id}><td>{item.assignment_title}</td><td>{item.student_name}</td><td>{new Date(item.submitted_at).toLocaleString('ru-RU')}</td><td><Link href={`/teacher/submissions/${item.id}/review`}>Проверить →</Link></td></tr>)}</tbody></table></div>:!error&&<p>Нет работ, ожидающих проверки.</p>}</AppShell>;
}
