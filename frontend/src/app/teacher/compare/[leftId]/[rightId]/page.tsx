"use client";
import { useParams } from 'next/navigation';
import { AppShell } from '../../../../../components/app-shell';
import { ArchiveOriginal } from '../../../../../components/assignment/archive-original';
export default function CompareOriginals(){const {leftId,rightId}=useParams<{leftId:string;rightId:string}>();return <AppShell><section className="academic-heading"><div><div className="eyebrow">СРАВНЕНИЕ ДОКУМЕНТОВ</div><h1>Две работы рядом</h1><p>Листайте документы независимо. PDF открывается в оригинальном виде, другие форматы — как извлечённые разделы с возможностью скачать файл.</p></div></section><div className="compare-originals"><ArchiveOriginal key={leftId} id={leftId} pageParam="leftPage"/><ArchiveOriginal key={rightId} id={rightId} pageParam="rightPage"/></div></AppShell>;}
