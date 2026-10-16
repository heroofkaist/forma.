"use client";
import {useCallback,useEffect,useState} from 'react';
import {downloadAuthenticatedFile} from '../lib/api';
import {platformRequest} from '../lib/platform';
import {briefFileError,uploadAssignmentBrief} from '../lib/assignment-brief';
type Brief={id:string;file_name:string;proposed_questions:{id:string;title:string;statement:string}[];approved_questions:{id:string;title:string;statement:string}[];warnings:string[]};
export function AssignmentBriefs({assignmentId}:{assignmentId:string}){
 const [items,setItems]=useState<Brief[]>([]),[file,setFile]=useState<File|null>(null),[message,setMessage]=useState(''),[busy,setBusy]=useState(false);
 const load=useCallback(()=>platformRequest<{items:Brief[]}>(`/api/assignment-briefs/${assignmentId}`).then(data=>setItems(data.items)),[assignmentId]);
 useEffect(()=>{void load().catch(()=>setMessage('Не удалось загрузить условия задания.'));},[load]);
 async function upload(){if(!file||busy)return;setBusy(true);setMessage('');try{await uploadAssignmentBrief(assignmentId,file);await load();setFile(null);setMessage('Условия сохранены. ИИ учтёт их при следующем разборе и проверке; критерии и баллы сохранены.');}catch(e){setMessage(e instanceof Error?e.message:'Не удалось сохранить файл.');}finally{setBusy(false);}}
 return <section className="platform-panel assignment-brief-list"><h3>Файлы условий</h3><p>ИИ использует эти материалы вместе с описанием и критериями задания. Загрузка файла не запускает платный анализ.</p>{items.map(item=><article key={item.id}><strong>{item.file_name}</strong><button type="button" className="quiet-button" onClick={()=>void downloadAuthenticatedFile(`/api/assignment-briefs/${assignmentId}/files/${item.id}`,item.file_name).catch(()=>setMessage('Не удалось скачать условия.'))}>Скачать условия</button>{!item.proposed_questions.length&&<small>Если в файле скан, его чтение зависит от доступного бюджета изображений.</small>}</article>)}<details><summary>{items.length?'Добавить условия':'Прикрепить файл условий · необязательно'}</summary><label>PDF, DOCX или PPTX<input type="file" accept=".pdf,.docx,.pptx" disabled={busy} onChange={e=>{const value=e.target.files?.[0]??null;setFile(value);setMessage(value?briefFileError(value)??'':'');}}/></label><button type="button" className="button" disabled={busy||!file||Boolean(file&&briefFileError(file))} onClick={()=>void upload()}>{busy?'Сохраняем…':'Сохранить файл условий'}</button></details>{message&&<p role="status">{message}</p>}</section>;
}
