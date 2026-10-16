import type { IntegritySummary } from './document-integrity';
import type { SubmissionSummary } from './submission-status';
export type TextSimilarity = {analysis_status:string;match_ratio:number|null;candidate_count:number|null};
export type ArchiveFileSummary={status:string;score:number|null;candidate_id?:string|null;identical_file?:boolean;checked:number;total:number|null;coverage_complete:boolean;stale:boolean};
export type AssignmentWork = SubmissionSummary & {id:string;student_id:string;student_name:string;file_name:string;file_type:string;archive_files?:ArchiveFileSummary;attention?:{kind:string;label:string;count:number;question_id?:string;criterion_id?:string};submitted_at:string;similarity:TextSimilarity;integrity?:IntegritySummary};
export type AssignmentWorkspace = {comparison_revision:string;id:string;title:string;description:string;assignment_type:string;offering_id:string;course_name:string;course_code:string;maximum_score:number;due_at:string|null;originality_enabled:boolean;students:{student_id:string;student_name:string;active:boolean}[];items:AssignmentWork[]};
export type StudentWork = AssignmentWorkspace['students'][number] & {attempts:AssignmentWork[];latest:AssignmentWork|null};
export type WorkFilter='all'|'missing'|'unreviewed'|'reviewed'|'attention'|'ready';
export function studentWorks(data:AssignmentWorkspace):StudentWork[]{
  const items=Array.isArray(data.items)?data.items:[];
  // Older API responses contain submissions but no enrollment roster.
  const roster=Array.isArray(data.students)?data.students:Array.from(new Map(items.map(w=>[w.student_id,{student_id:w.student_id,student_name:w.student_name||w.student_id,active:true}])).values());
  return roster.map(s=>{const attempts=items.filter(w=>w.student_id===s.student_id).sort((a,b)=>new Date(b.submitted_at).getTime()-new Date(a.submitted_at).getTime()||b.id.localeCompare(a.id));return{...s,attempts,latest:attempts[0]??null};});
}
export function filterStudentWorks(rows:StudentWork[],query:string,filter:WorkFilter){
  const text=query.trim().toLocaleLowerCase('ru');
  return rows.filter(row=>(!text||[row.student_name,row.student_id,...row.attempts.map(w=>w.file_name)].some(s=>s.toLocaleLowerCase('ru').includes(text)))&&
    (filter==='all'||filter==='attention'&&row.latest&&['processing','evidence','draft','outdated'].includes(row.latest.attention?.kind??'')||filter==='ready'&&row.latest?.attention?.kind==='ready'||filter==='missing'&&!row.latest||filter==='unreviewed'&&row.latest&&!['confirmed','published'].includes(row.latest.review_status)||filter==='reviewed'&&row.latest&&['confirmed','published'].includes(row.latest.review_status)));
}
export function textSimilarityLabel(value?:TextSimilarity){
  if(value?.analysis_status==='completed'&&typeof value.match_ratio==='number'&&Number.isFinite(value.match_ratio)&&value.match_ratio>=0&&value.match_ratio<=1)return `${Math.round(value.match_ratio*100)}%`;
  return ({failed:'Ошибка сравнения',insufficient_text:'Недостаточно текста',no_sources:'Нет источников',disabled:'Отключено',queued:'В очереди',analyzing:'Сравнивается',incomplete:'Неполный отчёт'} as Record<string,string>)[value?.analysis_status??'']??'Не сравнивалось';
}
export type Signal={status:string;score:number|null;identical_file?:boolean;partial?:boolean;evidence:(string|{current:{page?:number|null;asset?:string;unit?:string;quote?:string;start?:number;end?:number};candidate:{page?:number|null;asset?:string;unit?:string;quote?:string;start?:number;end?:number};score?:number;identical_thumbnail?:boolean;matched_words?:number;method?:string;inliers?:number;current_region?:{x:number;y:number;width:number;height:number};candidate_region?:{x:number;y:number;width:number;height:number}})[];source_evidence?:{concept:string;current:{unit:number;quote:string}|null;candidate:{unit:number;quote:string}|null}[]};
export type Comparison={id?:string;status:string;created_at?:string;stale:boolean;operator_context?:string;context?:string;version?:string;documents:{id:string;student_id:string;file_name:string;file_type?:string;truncated:boolean;units_total?:number;visual_units?:number;text_chars?:number}[];pairs:{submission_id:string;candidate_id:string;metrics:Record<string,Signal>}[]};
export const signalLabels:Record<string,string>={passages:'Длинные совпадающие фрагменты',text:'Сходство словаря · дополнительно',visual:'Страницы и изображения',formula:'Формулы',code:'Структура кода',semantic:'Содержание · Qwen'};
export function signalScore(metric?:Signal){return metric?.status==='completed'&&typeof metric.score==='number'&&Number.isFinite(metric.score)&&metric.score>=0&&metric.score<=1?metric.score:null;}
export function fileMatchFor(id:string,comparison?:Comparison|null){
  if(!comparison||comparison.stale||comparison.status!=='completed')return null;
  const matches=comparison.pairs.filter(pair=>pair.submission_id===id||pair.candidate_id===id).map(pair=>({score:signalScore(pair.metrics.document),candidateId:pair.submission_id===id?pair.candidate_id:pair.submission_id})).filter((match):match is {score:number;candidateId:string}=>match.score!==null).sort((a,b)=>b.score-a.score);
  return matches[0]??null;
}
export function comparisonUrl(left:string,right:string){return `/teacher/compare/${encodeURIComponent(left)}/${encodeURIComponent(right)}`;}
