"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowDown, ArrowRight, ArrowUpRight, CornerDownRight, Plus } from "lucide-react";
import { FormaMark } from "../components/forma-mark";
import { FormStudy } from "../components/form-study";
import { useAuth } from "../components/auth-provider";
import { homeForRole } from "../lib/navigation";

const readings = [
  { title: "Увидеть оригинал", label: "01 / ИСХОДНАЯ ТОЧКА", body: "Мысль начинается с самой работы. Оригинальный документ всегда рядом: можно вернуться к странице и проверить контекст.", note: "Слова студента — без подмены интерпретацией.", status: "ОРИГИНАЛ · СТРАНИЦА 1" },
  { title: "Найти основания", label: "02 / ВНИМАТЕЛЬНОЕ ЧТЕНИЕ", body: "Предложения ИИ связаны с критериями и свидетельствами. Сопоставляйте вывод с работой, проверяйте аргументы, задавайте вопросы.", note: "Формула и единицы указаны. Связь с условием требует проверки.", status: "ПРЕДЛОЖЕНИЕ ИИ · НЕ ОЦЕНКА" },
  { title: "Принять решение", label: "03 / ВАША ТОЧКА ЗРЕНИЯ", body: "Принять, изменить, отклонить или вернуться позже. Сохраните черновик, подтвердите критерии и отдельно опубликуйте готовое решение.", note: "Преподаватель определяет баллы и момент публикации.", status: "РЕШЕНИЕ ЧЕЛОВЕКА · ЕЩЁ НЕ ОПУБЛИКОВАНО" },
];

export default function HomePage() {
  const { user } = useAuth();
  const destination = user ? homeForRole(user.role) : "/login";
  const [reading, setReading] = useState(0);
  return <main className="bureau">
    <a className="skip-link" href="#thought">К содержанию</a>
    <header className="bureau-nav">
      <Link className="bureau-brand" href="/" aria-label="Forma — главная"><FormaMark/>forma<span className="brand-square"/></Link>
      <span className="bureau-descriptor">ПРОВЕРКА РАБОТ<br/>И УЧЕБНЫЕ КУРСЫ</span>
      <nav aria-label="О Forma"><a href="#method">Как это работает</a><a href="#people">Для кого</a></nav>
      <Link href={destination} className="bureau-entry">{user ? "К работе" : "Войти"}<ArrowUpRight size={19}/></Link>
    </header>

    <section className="bureau-hero" id="thought">
      <div className="hero-topline"><span><span className="signal-square"/> КУРСЫ, ЗАДАНИЯ И ОБРАТНАЯ СВЯЗЬ</span><span>РАБОТА → ПРОВЕРКА → ОЦЕНКА</span></div>
      <div className="hero-composition">
        <div className="hero-copy"><h1>У мысли<br/>есть <span className="hero-small-mark" aria-hidden="true">↗</span><br/><span className="hero-form">форма.</span></h1><p>Создавайте задания, собирайте работы<br/>и проверяйте их по критериям.<br/>Все материалы и оценки — в одном месте.</p><Link className="bureau-cta" href={destination}>В рабочее пространство<ArrowUpRight size={21}/></Link></div>
        <div className="hero-object"><FormStudy/></div>
        <span className="hero-margin">МАТЕМАТИКА / ЭССЕ / ЛАБОРАТОРНЫЕ</span>
      </div>
      <div className="hero-bottom"><a href="#method"><span className="index-circle">01</span>КАК ЭТО РАБОТАЕТ<ArrowDown size={18}/></a><p>ИИ предлагает.<br/><strong>Вы решаете.</strong></p><span className="hero-footnote">СОЗДАНО ДЛЯ ПРЕПОДАВАТЕЛЕЙ<br/>И ТЕХ, КТО УЧИТСЯ.</span></div>
    </section>

    <section className="bureau-method" id="method">
      <div className="section-register"><span>01 — МЕТОД FORMA</span><span>ТРИ ЭТАПА ПРОВЕРКИ</span><Plus size={18}/></div>
      <div className="method-heading"><h2>От ответа<br/>к <span>пониманию.</span></h2><p>Откройте работу, проверьте критерии<br/>и оставьте обратную связь.<br/>Студент увидит оценку после публикации.</p></div>
      <div className="reading-desk">
        <div className="reading-navigation"><div className="reading-tabs" role="group" aria-label="Этапы проверки">{readings.map((item, i) => <button key={item.title} onClick={() => setReading(i)} aria-pressed={reading === i}><span>0{i + 1}</span><strong>{item.title}</strong><ArrowUpRight size={22}/></button>)}</div><div className="reading-explanation" aria-live="polite"><span className="micro-label">{readings[reading].label}</span><p>{readings[reading].body}</p><CornerDownRight size={30}/></div></div>
        <div className="document-study"><div className="document-study-label"><span>УЧЕБНЫЙ ПРИМЕР / СИНТЕТИЧЕСКИЕ ДАННЫЕ</span><span>Ф / 01</span></div><div className="study-page"><div className="study-page-head"><span>ФИЗИКА</span><span>ЗАКОНЫ ДВИЖЕНИЯ</span></div><h3>Всё начинается<br/>с наблюдения.</h3><p>Масса тела — 2 кг.<br/>Ускорение — 3 м/с².</p><div className="study-equation">F = ma = <span>6 Н<svg viewBox="0 0 130 70" aria-hidden="true"><ellipse cx="65" cy="35" rx="60" ry="29" transform="rotate(-8 65 35)"/></svg></span></div><blockquote>«Сила направлена по ускорению»</blockquote><div className="study-note"><span>↳</span><p>{readings[reading].note}</p></div></div><div className="document-study-status"><span className="signal-square"/>{readings[reading].status}</div></div>
      </div>
    </section>

    <section className="bureau-manifesto" id="principle"><div className="section-register"><span>02 — ПРИНЦИП</span><span>ИНТЕРПРЕТАЦИЯ ≠ ОЦЕНКА</span><Plus size={18}/></div><div className="manifesto-body"><div className="manifesto-aside"><FormaMark/><p>ИИ ПОМОГАЕТ<br/>ПРОВЕРЯТЬ РАБОТЫ.</p><span>ОЦЕНКУ УТВЕРЖДАЕТ<br/>ПРЕПОДАВАТЕЛЬ.</span></div><h2>Последнее<br/>слово —<br/><span>ваше<svg viewBox="0 0 600 32" preserveAspectRatio="none" aria-hidden="true"><path d="M4 17Q240 0 595 13M65 28Q340 10 540 25"/></svg>.</span></h2></div><div className="manifesto-bottom"><span>ЧЕЛОВЕК В ЦЕНТРЕ РЕШЕНИЯ ↗</span><p>Предложение можно проверить. Балл — изменить.<br/>С выводом можно не согласиться.<br/>Оценка появляется у студента только после вашей публикации.</p></div></section>

    <section className="bureau-people" id="people"><div className="section-register"><span>03 — ДВЕ ПЕРСПЕКТИВЫ</span><span>ОБЩЕЕ ПРОСТРАНСТВО</span><Plus size={18}/></div><div className="people-heading"><h2>Для преподавателей<br/>и студентов.</h2><p>Понятный процесс.<br/>Внимательная обратная связь.</p></div><div className="people-grid"><article className="person-panel person-teacher"><div className="person-top"><span>ДЛЯ ПРЕПОДАВАТЕЛЯ</span><span>А / 01</span></div><h3>Создавайте задания.<br/>Проверяйте работы.<br/>Публикуйте оценки.</h3><p>Условия, работы студентов и критерии рядом.<br/>Проверку можно сохранить и продолжить позже.</p><Link href={destination}>Перейти к работе<ArrowUpRight size={27}/></Link></article><article className="person-panel person-student"><div className="person-top"><span>ДЛЯ СТУДЕНТА</span><span>Б / 02</span></div><h3>Открывайте задания.<br/>Отправляйте работы.<br/>Получайте отзывы.</h3><p>Собственный документ, понятный статус<br/>и обратная связь от преподавателя.</p><Link href={user ? destination : "/register"}>{user ? "Открыть пространство" : "Создать учётную запись"}<ArrowUpRight size={27}/></Link></article></div></section>

    <section className="bureau-faq"><div><span className="micro-label">ЧАСТЫЕ ВОПРОСЫ</span><h2>Вопросы<br/>и ответы.</h2><ArrowDown size={34}/></div><div>{[
      ["Forma выставляет оценки сама?", "Нет. ИИ предлагает интерпретации и баллы. Преподаватель проверяет основания, принимает собственное решение и отдельно публикует результат."],
      ["Какие работы можно отправлять?", "PDF, DOCX и PPTX; для заданий по программированию — также исходный код и ZIP. Предложения оценки по критериям доступны для PDF с задачами, эссе и лабораторными. Другие работы можно проверить вручную. Код не запускается."],
      ["Обязательно использовать готовый бланк?", "Нет. Студент отправляет собственный документ. Для PDF оригинал доступен постранично рядом с критериями проверки."],
    ].map(([question, answer], i) => <details key={question}><summary><span>0{i + 1}</span>{question}<Plus size={20}/></summary><p>{answer}</p></details>)}</div></section>

    <footer className="bureau-footer"><div className="footer-invitation"><span>ГОТОВЫ НАЧАТЬ?</span><Link href={destination}>За работу.<ArrowUpRight/></Link></div><div className="footer-wordmark" aria-hidden="true">forma<span>↗</span></div><div className="footer-colophon"><span>FORMA / УЧЕБНЫЕ КУРСЫ</span><span>ВНИМАНИЕ К РАБОТЕ.<br/>УВАЖЕНИЕ К МЫСЛИ.</span><a href="#thought">В НАЧАЛО<ArrowRight size={17}/></a></div></footer>
  </main>;
}
