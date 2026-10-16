"use client";
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {DocumentViewer,type EvidenceHighlight} from '../review/document-viewer';
import {platformRequest} from '../../lib/platform';
import {downloadAuthenticatedFile} from '../../lib/api';
import type {ReviewResponse} from '../../lib/review-workspace';
type OriginalData=Pick<ReviewResponse,'student_name'|'file_name'|'file_type'|'structure'>&{can_review:boolean};
export function ArchiveOriginal({id,pageParam='page'}:{id:string;pageParam?:string}){
 const [data,setData]=useState<OriginalData|null>(null),[error,setError]=useState(''),[page,setPage]=useState(1);
 const [highlight,setHighlight]=useState<EvidenceHighlight|null>(null);
 const base=`/api/course-archive/files/${id}`;
 useEffect(()=>{let active=true;platformRequest<OriginalData>(base).then(value=>{if(active){setData(value);const query=new URLSearchParams(window.location.search);const requested=Number(query.get(pageParam));const initial=Number.isInteger(requested)&&requested>=1&&requested<=(value.structure?.pages.length??0)?requested:1;setPage(initial);try{const raw=query.get(pageParam.replace('Page','Region'));if(raw){const box=JSON.parse(raw);if(['x','y','width','height'].every(key=>typeof box[key]==='number'&&Number.isFinite(box[key])&&box[key]>=0&&box[key]<=1)&&box.x+box.width<=1.001&&box.y+box.height<=1.001)setHighlight({page_number:initial,quote:'Сопоставляемая область изображения из отчёта о совпадениях.',rectangles:[box]});}}catch{/* A malformed optional highlight never prevents opening the original. */}}}).catch(()=>{if(active)setError('Не удалось открыть архивный файл. Проверьте доступ к курсу.');});return()=>{active=false;};},[base,pageParam]);
 async function download(){if(!data)return;try{await downloadAuthenticatedFile(`${base}/file`,data.file_name);}catch{setError('Не удалось скачать оригинал. Попробуйте ещё раз.');}}
 const pages=data?.structure?.pages??[];
 return <section><h2>{data?.student_name??'Оригинал работы'}</h2><p>{data?.file_name}</p>{error&&<p role="alert">{error}</p>}{!data&&!error&&<p role="status">Загружаем файл…</p>}{data&&<>{data.file_type==='pdf'?<DocumentViewer submissionId={id} resourceBase={base} fileName={data.file_name} fileType={data.file_type} pageCount={pages.length} page={page} onPage={setPage} highlight={highlight} onClearHighlight={()=>setHighlight(null)}/>:<div className="comparison-extracted"><div className="comparison-extracted-tools"><button className="quiet-button" disabled={page<=1} onClick={()=>setPage(v=>v-1)}>← Назад</button><span>Раздел {page} / {pages.length||'—'}</span><button className="quiet-button" disabled={page>=pages.length} onClick={()=>setPage(v=>v+1)}>Далее →</button><button className="quiet-button" onClick={()=>void download()}>Скачать оригинал</button></div><p className="muted">Извлечённое содержимое. Оформление и вложенные изображения смотрите в оригинале.</p><pre>{pages[page-1]?.text||'В этом разделе нет извлечённого текста.'}</pre></div>}{data.can_review&&<Link href={`/teacher/submissions/${id}/review`}>Перейти к проверке →</Link>}</>}</section>;
}
