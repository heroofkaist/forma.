"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenCheck, ClipboardList, GraduationCap, Library, ScanSearch } from "lucide-react";
import { useAuth } from "./auth-provider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { enabled, user, logout } = useAuth();
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <Link href="/" className="forma-brand"><span className="brand-mark"><GraduationCap size={17} /></span>forma<span className="brand-period">.</span></Link>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        {(!enabled || (user?.role === "teacher" || user?.role === "account")) && (
          <nav className="side-nav">
            <Link className={pathname === "/" || pathname.startsWith("/assignments") ? "side-link active" : "side-link"} href="/"><ClipboardList size={16} />Задания</Link>
            <Link className={pathname.startsWith("/teacher") ? "side-link active" : "side-link"} href="/teacher"><BookOpenCheck size={16} />Курсы</Link>
            <Link className={pathname.startsWith("/teacher/archive") ? "side-link active" : "side-link"} href="/teacher/archive"><Library size={16} />Архив</Link>
            <Link className={pathname.startsWith("/teacher/originality") || pathname.includes("/originality") ? "side-link active" : "side-link"} href="/teacher/originality"><ScanSearch size={16} />Оригинальность</Link>
            {(!enabled || user?.role === "account") && <Link className="side-link" href="/student"><GraduationCap size={16} />Вид студента</Link>}
            {user?.role === "account" && <Link className="side-link" href="/settings/profile">Настройки</Link>}
          </nav>
        )}
        <div className="sidebar-foot"><span className="ready-dot" />{enabled ? user?.username : "ДЕМО · без входа"}</div>
      </aside>
      <main className="main-column">
        <header className="global-header">
          <div className="breadcrumbs"><span>Forma</span><span className="crumb-sep">/</span><span>{pathname.includes("/review") ? "Проверка" : pathname.includes("/template") ? "Шаблон" : pathname.includes("/results") ? "Результаты" : pathname.includes("/new") ? "Новое задание" : "Задания"}</span></div>
          {enabled && <button className="quiet-button" onClick={logout}>Выйти</button>}
        </header>
        <div className="workspace">{children}</div>
      </main>
    </div>
  );
}

export function StatusLabel({ status }: { status: string }) {
  const labels: Record<string, string> = {
    pending: "Ожидает",
    processing: "Обрабатывается",
    ready_for_review: "К проверке",
    needs_attention: "Нужно внимание",
    failed: "Ошибка",
    approved: "Проверено",
  };
  return <span className={`status-label status-${status}`}>{labels[status] ?? status}</span>;
}
