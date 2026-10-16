import { API_URL, authenticatedFetch } from './api';
import { platformRequest } from './platform';
export function briefFileError(file: Pick<File,'name'|'size'>) {
  if(!/\.(pdf|docx|pptx)$/i.test(file.name)) return 'Для условий задания выберите PDF, DOCX или PPTX.';
  if(!file.size || file.size>30*1024*1024) return 'Файл условий должен быть непустым и не больше 30 МБ.';
  return null;
}
export async function uploadAssignmentBrief(assignmentId:string,file:File) {
  const issue=briefFileError(file);if(issue)throw new Error(issue);
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))).map(n=>n.toString(16).padStart(2,'0')).join('');
  const path=`/api/assignment-briefs/${assignmentId}`;
  const saved=await platformRequest<{items:{id:string;content_hash?:string}[]}>(path);
  const existing=saved.items.find(f=>f.content_hash===digest);if(existing)return existing;
  const form=new FormData();form.append('file',file);
  const response=await authenticatedFetch(`${API_URL}${path}`,{method:'POST',body:form});
  const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Не удалось сохранить файл условий.');
  return data as {id:string};
}
