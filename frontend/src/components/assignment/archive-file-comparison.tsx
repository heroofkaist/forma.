"use client";
import Link from 'next/link';
import {useEffect,useRef,useState} from 'react';
import {similarityLabel} from '../../lib/teacher-display';
import {platformRequest} from '../../lib/platform';
import {type Comparison,type ArchiveFileSummary} from '../../lib/assignment-workspace';
import {ComparisonReport} from './comparison-report';

export function ArchiveMatchSignal({submissionId,value}:{submissionId:string;value?:ArchiveFileSummary}) {
  const score=value?.score;
  const valid=typeof score==='number'&&Number.isFinite(score)&&score>=0&&score<=1&&!value?.stale;
  const matched=valid&&score>0;
  return <div className={`archive-match-signal ${matched?'has-archive-match':''}`}><Link className="assignment-text-score" href={`/teacher/archive/${submissionId}#archive-files`}>{valid?similarityLabel(score):value?.stale?'Нужно обновить':value?.status==='no_sources'?'Нет других работ':value?.coverage_complete?'Нужна ручная проверка':'Сравнить с архивом'}</Link><small>{matched?value?.identical_file?'Файлы идентичны · откройте источник':score>=.75?'Сильное совпадение · проверьте источник':'Найдены совпадающие фрагменты':valid?'Индекс сходства файлов':'Страницы, изображения, текст и код'}</small>{value&&!value.coverage_complete&&value.checked>0&&<small>Проверено {value.checked} из {value.total??'—'}. Архив проверен не полностью.</small>}</div>;
}

type ArchiveScan=Comparison&{corpus_key:string;checked:number;compared:number;total:number;remaining:number;coverage_complete:boolean;skipped:{id:string;reason:string}[];scope:string;baseline_limit:boolean;insufficient_count?:number;partial_count?:number};
export function ArchiveScanButton({works,onResult}:{works:{id:string;name:string}[];onResult:(id:string,result:ArchiveFileSummary)=>void}) {
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState('');
  const active=useRef(false),stop=useRef(false),alive=useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;stop.current=true;};},[]);
  async function run(){if(active.current)return;active.current=true;stop.current=false;setBusy(true);setError('');
    try{for(let i=0;i<works.length&&!stop.current&&alive.current;i++){
      const work=works[i],path=`/api/assignment-comparison/archive/${work.id}`;let report=await platformRequest<ArchiveScan>(path);
      do{if(report.remaining>0)report=await platformRequest<ArchiveScan>(path,{expected_corpus:report.corpus_key});
        if(!alive.current)break;
        const best=[...report.pairs].sort((a,b)=>(b.metrics.document?.score??-1)-(a.metrics.document?.score??-1))[0];const metric=best?.metrics.document;
        onResult(work.id,{status:report.status,score:metric?.score??(report.compared>0?0:null),candidate_id:best?.submission_id===work.id?best.candidate_id:best?.submission_id,
          identical_file:metric?.identical_file,checked:report.checked,total:report.total,coverage_complete:report.coverage_complete,stale:report.stale});
        setMessage(`${work.name} · работа ${i+1} из ${works.length}: проверено ${report.checked} из ${report.total} архивных файлов.`);
      }while(report.remaining>0&&!stop.current&&alive.current);
    }}catch(e){if(alive.current)setError(e instanceof Error?e.message:'Не удалось продолжить сравнение. Сохранённый прогресс доступен.');}
    finally{active.current=false;if(alive.current){setBusy(false);if(stop.current)setMessage('Сравнение остановлено. Прогресс сохранён; можно продолжить.');}}
  }
  return <div className="archive-bulk-scan"><button className="button" disabled={busy||!works.length} onClick={()=>void run()}>{busy?'Сравниваем с архивом…':'Проверить архив для всех работ'}</button>{busy&&<button className="quiet-button" onClick={()=>{stop.current=true;}}>Остановить после текущего файла</button>}{message&&<p role="status">{message}</p>}{error&&<p role="alert" className="notice error-notice">{error}</p>}<small>Страницы, рисунки, текст и код · локально · прогресс сохраняется</small></div>;
}
export function ArchiveFileComparison({submissionId}:{submissionId:string}) {
  const [result,setResult]=useState<ArchiveScan|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[retry,setRetry]=useState(0),[loading,setLoading]=useState(true);
  const sending=useRef(false),paused=useRef(false),alive=useRef(true),generation=useRef(0);
  const path=`/api/assignment-comparison/archive/${submissionId}`;
  useEffect(()=>{let active=true;generation.current++;alive.current=true;sending.current=false;setBusy(false);setLoading(true);setResult(null);setError('');void platformRequest<ArchiveScan>(path).then(value=>{if(active)setResult(value);}).catch(()=>{if(active)setError('Не удалось загрузить сравнение файлов с архивом.');}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;alive.current=false;paused.current=true;generation.current++;};},[path,retry]);
  async function run(){if(sending.current||!result)return;sending.current=true;paused.current=false;setBusy(true);setError('');let current=result;const ticket=generation.current;
    try{do{const next=await platformRequest<ArchiveScan>(path,{expected_corpus:current.corpus_key,retry_unavailable:current.remaining===0&&current.skipped.length>0});current=next;if(alive.current&&ticket===generation.current)setResult(next);if(next.remaining===0)break;}while(!paused.current&&alive.current&&ticket===generation.current);}
    catch(e){if(alive.current&&ticket===generation.current)setError(e instanceof Error?e.message:'Сравнение прервано. Уже проверенные файлы сохранены; можно продолжить.');}
    finally{if(ticket===generation.current){sending.current=false;if(alive.current)setBusy(false);}}
  }
  const hasMatch=result?.pairs.some(pair=>typeof pair.metrics.document?.score==='number'&&pair.metrics.document.score>0);
  return <section id="archive-files" className={`archive-file-scan ${hasMatch?'has-archive-match':''}`} aria-labelledby="archive-files-title"><div className="assignment-section-heading"><div><div className="eyebrow">ФАЙЛЫ · АРХИВ КУРСА</div><h2 id="archive-files-title">Совпадения с другими работами</h2><p>Сравниваем страницы и изображения, длинные фрагменты текста, формулы и структуру кода. Учитываем прошлые потоки и связанные курсы.</p></div><div className="comparison-run-actions"><button className="button primary" disabled={loading||busy||!result||result.total===0||(result.coverage_complete||(result.remaining===0&&result.skipped.length===0&&Boolean(result.partial_count)))} onClick={()=>void run()}>{busy?'Сравниваем файлы…':result?.partial_count&&result.remaining===0?'Нужна ручная проверка':result?.coverage_complete?'Архив проверен':result?.skipped.length&&result.remaining===0?'Повторить для недоступного файла':result?.checked?'Продолжить сравнение':'Сравнить с архивом курса'}</button>{busy&&<button className="button" onClick={()=>{paused.current=true;}}>Остановить после текущего файла</button>}<small>Локальная проверка · без расходов на ИИ</small></div></div>
    {loading&&<p role="status">Загружаем сохранённый отчёт…</p>}{error&&<p className="notice error-notice" role="alert">{error} <button className="quiet-button" disabled={busy} onClick={()=>setRetry(v=>v+1)}>Обновить состояние</button></p>}
    {result&&<><p className="archive-scan-progress" role="status">Проверено {result.checked} из {result.total} файлов других авторов. Сопоставлено: {result.compared}.{result.remaining>0?' Сравнение архива ещё не завершено.':''}</p>{result.total>0&&<progress value={result.checked} max={result.total} aria-label="Проверено архивных файлов"/>}
      {result.stale&&<p className="notice">Архив или материалы задания изменились. Запустите новое сравнение; прежний результат не используется как актуальный.</p>}
      {result.total===0&&<p>В этом архиве пока нет работ других авторов. Проверьте, связан ли курс с прошлыми потоками.</p>}
      {hasMatch&&<div className="archive-match-warning"><strong>Найдены совпадения с архивом</strong><p>Откройте конкретные фрагменты и оригиналы. Красная отметка означает найденное совпадение; решение о списывании принимает преподаватель с учётом условий, шаблона и допустимых источников.</p></div>}
      {!hasMatch&&result.coverage_complete&&<p>{result.compared>0?'В проверенных файлах сопоставимых совпадений не найдено.':'Для этих файлов недостаточно сопоставимых признаков. Оригиналы требуют ручной проверки.'}</p>}
      {Boolean(result.partial_count)&&<p className="notice error-notice">Для {result.partial_count} пар достигнут лимит текста или поиска. Отчёт неполный: проверьте оставшуюся часть оригиналов вручную.</p>}
      {Boolean(result.insufficient_count)&&<p className="notice">Для {result.insufficient_count} файлов недостаточно сопоставимых признаков. Их содержимое нужно проверить вручную.</p>}
      {result.skipped.length>0&&<p className="notice error-notice">Не удалось сопоставить файлов: {result.skipped.length}. Проверка неполная; это не нулевое сходство. Откройте эти оригиналы в архиве.{result.skipped.map(item=><Link key={item.id} href={`/teacher/archive/${item.id}`} target="_blank" rel="noopener noreferrer"> Открыть недоступный файл ↗</Link>)}</p>}
      {result.baseline_limit&&<p className="notice">Не все материалы задания поместились в лимит исключений. Проверьте совпавшие фрагменты условия или шаблона вручную.</p>}
      <ComparisonReport result={result}/><p className="muted">{result.scope} Индекс сходства не определяет направление заимствования. Переписанные от руки решения и пересказ своими словами могут остаться незамеченными.</p>
    </>}
  </section>;
}
