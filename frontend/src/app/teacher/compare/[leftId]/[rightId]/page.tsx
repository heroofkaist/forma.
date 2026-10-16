"use client";
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { AppShell } from '../../../../../components/app-shell';
import { DocumentViewer } from '../../../../../components/review/document-viewer';
import { platformRequest } from '../../../../../lib/platform';
import { downloadAuthenticatedFile } from '../../../../../lib/api';
import type { ReviewResponse } from '../../../../../lib/review-workspace';
function Original({id}:{id:string}) {
 const [data,setData]=useState<ReviewResponse|null>(null),[error,setError]=useState(''),[page,setPage]=useState(1);
 useEffect(()=>{let active=true;platformRequest<ReviewResponse>(`/api/document-review/${id}`).then(value=>{if(active)setData(value);}).catch(()=>{if(active)setError('Не удалось открыть оригинал. Проверьте доступ.');});return()=>{active=false;};},[id]);
 async function download(){if(!data)return;try{await downloadAuthenticatedFile(`/api/submission-files/${id}`,data.file_name);}catch{setError('Не удалось скачать оригинал. Попробуйте ещё раз.');}}
 const pages=data?.structure?.pages??[];
 return <section><h2>{data?.student_name??'Оригинал работы'}</h2><p>{data?.file_name}</p>{error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">Загружаем файл…</p>}{data&&<>{data.file_type==='pdf'?<DocumentViewer submissionId={id} fileName={data.file_name} fileType={data.file_type} pageCount={pages.length} page={page} onPage={setPage}/>:<div className="comparison-extracted"><div className="comparison-extracted-tools"><button className="quiet-button" disabled={page<=1} onClick={()=>setPage(v=>v-1)}>← Назад</button><span>Раздел {page} / {pages.length||'—'}</span><button className="quiet-button" disabled={page>=pages.length} onClick={()=>setPage(v=>v+1)}>Далее →</button><button className="quiet-button" onClick={()=>void download()}>Скачать оригинал</button></div><p className="muted">Извлечённое содержимое. Оформление и вложенные изображения смотрите в оригинале.</p><pre>{pages[page-1]?.text||'В этом разделе нет извлечённого текста.'}</pre></div>}<Link href={`/teacher/submissions/${id}/review`}>Перейти к проверке →</Link></>}</section>;
}
export default function CompareOriginals(){const {leftId,rightId}=useParams<{leftId:string;rightId:string}>();return <AppShell><section className="academic-heading"><div><div className="eyebrow">СРАВНЕНИЕ ДОКУМЕНТОВ</div><h1>Две работы рядом</h1><p>Листайте документы независимо. PDF открывается в оригинальном виде, другие форматы — как извлечённые разделы с возможностью скачать файл.</p></div></section><div className="compare-originals"><Original key={leftId} id={leftId}/><Original key={rightId} id={rightId}/></div></AppShell>;}
