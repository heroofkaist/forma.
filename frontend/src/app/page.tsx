"use client";

import Link from "next/link";
import { ArrowRight, ArrowUpRight, BookOpen, ClipboardCheck, ScanSearch, Check } from "lucide-react";
import { FormaMark } from "../components/forma-mark";
import { ProductTour } from "../components/product-tour";
import { useAuth } from "../components/auth-provider";
import { homeForRole } from "../lib/navigation";

export default function HomePage() {
  const { user } = useAuth();
  const destination = user ? homeForRole(user.role) : "/login";
  return <div className="forma-public">
    <a className="skip-link" href="#main-content">К содержанию</a>
    <header className="public-header"><Link className="forma-brand" href="/" aria-label="Forma · главная"><FormaMark/>forma<span className="brand-period">.</span></Link><nav aria-label="О Forma"><a href="#workflow">Как это работает</a><a href="#possibilities">Возможности</a></nav><Link className="button primary" href={destination}>{user ? "Моё пространство" : "Войти"}<ArrowUpRight size={17} aria-hidden="true"/></Link></header>
    <main id="main-content" tabIndex={-1}>
      <section className="public-hero"><div className="public-hero-copy"><span className="public-kicker"><span aria-hidden="true"/>Для преподавателей и студентов</span><h1>Больше внимания<br/>к каждой <em>работе.</em></h1><p>Курсы, работы студентов и проверка с ИИ.<br/>От первого задания до понятной обратной связи.</p><div className="public-hero-actions"><Link className="button primary" href={destination}>Открыть Forma<ArrowRight size={19} aria-hidden="true"/></Link><a className="public-text-link" href="#workflow">Посмотреть, как это работает</a></div><div className="public-assurance"><Check size={16} aria-hidden="true"/>ИИ предлагает баллы. Итоговую оценку ставите вы.</div></div><div className="public-hero-aside"><span className="public-aside-index">Меньше переключений.<br/><strong>Больше смысла.</strong></span><div className="public-document-stack" aria-hidden="true"><div/><div/><div><FormaMark/><span>От работы<br/>к пониманию.</span><i>forma / учебное пространство</i></div></div></div></section>
      <section className="public-workflow" id="workflow"><div className="public-section-heading"><div><span className="eyebrow">ПРОВЕРКА БЕЗ ЛИШНИХ ШАГОВ</span><h2>Всё, что нужно для решения.<br/>В одном окне.</h2></div><p>Читайте оригинал, сверяйте баллы с критериями и оставляйте комментарии. Контекст остаётся перед глазами.</p></div><ProductTour/></section>
      <section className="public-capabilities" id="possibilities"><div className="public-section-heading"><div><span className="eyebrow">ОТ ЗАДАНИЯ ДО РЕЗУЛЬТАТА</span><h2>Порядок в учебной работе.</h2></div></div><div className="public-capability-grid"><article><BookOpen size={24} aria-hidden="true"/><h3>Курсы и задания</h3><p>Условия, сроки, файлы и критерии. Студентам понятно, что отправить и как будет оцениваться работа.</p><span>Создать → собрать → проверить</span></article><article><ClipboardCheck size={24} aria-hidden="true"/><h3>Проверка по критериям</h3><p>ИИ учитывает задание и предлагает баллы с обоснованием. Вы проверяете, меняете и подтверждаете результат.</p><span>Каждый балл можно объяснить</span></article><article><ScanSearch size={24} aria-hidden="true"/><h3>Совпадения с архивом</h3><p>Сопоставляйте файлы, фрагменты текста и изображения. Открывайте источники, чтобы проверить контекст совпадений.</p><span>Основания для внимательной проверки</span></article></div></section>
      <section className="public-statement"><span className="eyebrow">ЧЕЛОВЕК ПРИНИМАЕТ РЕШЕНИЕ</span><h2>Технология помогает.<br/><em>Преподаватель решает.</em></h2><p>Предложения ИИ, совпадения и признаки машинного текста помогают обратить внимание на работу. Выводы и оценка остаются за преподавателем.</p><Link className="button" href={destination}>Перейти к работе<ArrowRight size={18} aria-hidden="true"/></Link></section>
      <section className="public-faq"><h2>Перед началом</h2><div>{[["Кто видит предварительные баллы?", "Только преподаватель. Студент получает оценку и комментарии после публикации."],["Какие файлы можно отправить?", "PDF, DOCX и PPTX. Для программирования — также исходный код и ZIP. ИИ предлагает оценку по критериям для PDF с задачами, эссе и лабораторными; другие работы можно проверить вручную."],["Нужен ли обязательный шаблон?", "Это определяет преподаватель при создании задания. Можно прикрепить обязательный шаблон, предложить его по желанию или разрешить собственное оформление."]].map(([question, answer]) => <details key={question}><summary>{question}</summary><p>{answer}</p></details>)}</div></section>
    </main>
    <footer className="public-footer"><Link className="forma-brand" href="/"><FormaMark/>forma<span className="brand-period">.</span></Link><span>Внимание к работе. Уважение к мысли.</span><Link href={destination}>{user ? "Моё пространство" : "Войти в Forma"}<ArrowUpRight size={16} aria-hidden="true"/></Link></footer>
  </div>;
}
