"use client";
import Link from 'next/link';
import {useParams} from 'next/navigation';
import {useEffect,useState} from 'react';
import {AppShell} from '../../../../../components/app-shell';
import {platformRequest} from '../../../../../lib/platform';
import {type QuestionQueue} from '../../../../../lib/review-pilot';
import {QuestionReviewQueue} from '../../../../../components/review/question-review-queue';
export default function QuestionReviewPage(){
  const {assignmentId}=useParams<{assignmentId:string}>();const [qid,setQid]=useState('');const [data,setData]=useState<QuestionQueue|null>(null);const [loading,setLoading]=useState(true);const [error,setError]=useState('');const [retry,setRetry]=useState(0);
  useEffect(()=>{let active=true;setLoading(true);setError('');void platformRequest<QuestionQueue>(`/api/review-pilot/assignments/${assignmentId}/question-queue${qid?'?'+new URLSearchParams({question_id:qid}):''}`).then(result=>{if(active){setData(result);if(!qid&&result.questions.length)setQid(result.questions[0].id);}}).catch(cause=>{if(active)setError(cause instanceof Error?cause.message:'Не удалось загрузить очередь.');}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[assignmentId,qid,retry]);
  return <AppShell><div className="academic-heading"><div><div className="eyebrow">ПРОВЕРКА ПО ВОПРОСАМ</div><h1>{data?.title ?? 'Один вопрос · вся группа'}</h1><p>Выберите вопрос и проверяйте его у всей группы подряд. В работе будут кнопки перехода к следующему студенту; весь оригинал остаётся доступен. Неполную проверку сохраняйте как черновик.</p><Link href={`/teacher/assignments/${assignmentId}/submissions`}>Все работы →</Link></div></div>{data && <label className="form-label">Вопрос<select value={qid} onChange={e=>setQid(e.target.value)}>{data.questions.map(q=><option key={q.id} value={q.id}>{q.title}</option>)}</select></label>}{loading?<p role="status">Загружаем очередь…</p>:error?<div role="alert" className="notice error-notice">{error}<button className="button" onClick={()=>setRetry(n=>n+1)}>Повторить</button></div>:data && (!data.questions.length?<p className="student-empty">В задании нет отдельных вопросов. Используйте обычную проверку из списка работ.</p>:<QuestionReviewQueue data={data} question={qid}/>)}</AppShell>;
}
