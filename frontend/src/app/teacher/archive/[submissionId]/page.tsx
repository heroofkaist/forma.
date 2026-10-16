"use client";
import {useParams} from 'next/navigation';
import {AppShell} from '../../../../components/app-shell';
import {ArchiveFileComparison} from "../../../../components/assignment/archive-file-comparison";
import {ArchiveOriginal} from '../../../../components/assignment/archive-original';
export default function ArchiveFile(){const {submissionId}=useParams<{submissionId:string}>();return <AppShell><section className="academic-heading"><div><div className="eyebrow">АРХИВ КУРСА</div><h1>Архивная работа</h1><p>Оригинал для сравнения с работами текущего и прошлых потоков.</p></div></section><ArchiveFileComparison submissionId={submissionId}/><ArchiveOriginal id={submissionId}/></AppShell>;}
