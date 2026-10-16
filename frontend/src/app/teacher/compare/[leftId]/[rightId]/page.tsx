"use client";
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { AppShell } from '../../../../../components/app-shell';
import { DocumentViewer } from '../../../../../components/review/document-viewer';
import { platformRequest } from '../../../../../lib/platform';
import type { ReviewResponse } from '../../../../../lib/review-workspace';
function Original({id}:{id:string}) {
 const [data,setData]=useState<ReviewResponse|null>(null),[error,setError]=useState(''),[page,setPage]=useState(1);
 useEffect(()=>{let active=true;platformRequest<ReviewResponse>(`/api/document-review/${id}`).then(value=>{if(active)setData(value);}).catch(()=>{if(active)setError('Не удалось открыть оригинал. Проверьте доступ.');});return()=>{active=false;};},[id]);
 return <section><h2>{data?.student_name??'Оригинал работы'}</h2><p>{data?.file_name}</p>{error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">Загружаем файл…</p>}{data&&<><DocumentViewer submissionId={id} fileName={data.file_name} fileType={data.file_type} pageCount={data.structure?.pages.length??0} page={page} onPage={setPage}/><Link href={`/teacher/submissions/${id}/review`}>Перейти к проверке →</Link></>}</section>;
}
export default function CompareOriginals(){const {leftId,rightId}=useParams<{leftId:string;rightId:string}>();return <AppShell><section className="academic-heading"><div><div className="eyebrow">СРАВНЕНИЕ ОРИГИНАЛОВ</div><h1>Две работы рядом</h1><p>Листайте документы независимо и сверяйте совпадения с оригиналами.</p></div></section><div className="compare-originals"><Original key={leftId} id={leftId}/><Original key={rightId} id={rightId}/></div></AppShell>;}
