"use client";
import {useCallback,useEffect,useState} from 'react';
import Link from 'next/link';
import {platformRequest} from '../lib/platform';
type ArchiveInfo={course_id:string;archive_key:string;course_count:number;submission_count:number;courses:{id:string;name:string;code:string;instructor:string;linked:boolean}[]};
export function CourseArchive({offeringId}:{offeringId:string}){
 const [info,setInfo]=useState<ArchiveInfo|null>(null),[target,setTarget]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const load=useCallback(()=>platformRequest<ArchiveInfo>(`/api/course-archive/${offeringId}`).then(setInfo),[offeringId]);
 useEffect(()=>{void load().catch(()=>setError('Не удалось загрузить архив курса.'));},[load]);
 async function link(){setBusy(true);setError('');try{await platformRequest(`/api/course-archive/${offeringId}/link`,{target_course_id:target});await load();setTarget('');}catch{setError('Не удалось связать архивы. Выберите курс своего учреждения.');}finally{setBusy(false);}}
 return <section className="platform-panel course-archive-card"><div><h2>Общий архив курса</h2><p>Работы сохраняются между потоками. Курсы одного учреждения с одинаковым кодом используют общую базу для сравнения.</p>{info&&<p><strong>{info.submission_count}</strong> работ · <strong>{info.course_count}</strong> связанных курсов</p>}{info&&<Link className="button" href={`/teacher/archive?course=${info.course_id}`}>Открыть архив курса →</Link>}</div>{info&&info.courses.some(c=>!c.linked)&&<details><summary>Связать курс с другим архивом</summary><p>Если один предмет завели под разными кодами, выберите его здесь. Работы обоих курсов станут доступны преподавателям для сравнения; оценки остаются у преподавателя.</p><label>Курс того же учреждения<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">Выберите курс</option>{info.courses.filter(c=>!c.linked).map(c=><option key={c.id} value={c.id}>{c.code} · {c.name} · {c.instructor}</option>)}</select></label><button className="button" disabled={busy||!target} onClick={()=>void link()}>Объединить архивы</button></details>}{error&&<p role="alert">{error}</p>}</section>;
}
