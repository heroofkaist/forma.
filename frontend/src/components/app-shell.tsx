"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenCheck, ClipboardList, GraduationCap, Library, ScanSearch } from "lucide-react";
import { teacherRole, locationForPath } from "../lib/navigation";
import { useAuth } from "./auth-provider";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const location = locationForPath(pathname);
  const { enabled, user, logout } = useAuth();
  return (
    <div className="app-frame">
      <aside className="sidebar">
        <Link href="/" className="forma-brand"><span className="brand-mark"><GraduationCap size={17} /></span>forma<span className="brand-period">.</span></Link>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        {(!enabled || teacherRole(user?.role)) && (
          <nav className="side-nav">
            <Link className={location.key === "assignments" ? "side-link active" : "side-link"} href="/"><ClipboardList size={16} />Задания</Link>
            <Link className={location.key === "courses" ? "side-link active" : "side-link"} href="/teacher"><BookOpenCheck size={16} />Курсы</Link>
            <Link className={location.key === "review" ? "side-link active" : "side-link"} href="/teacher/review"><ClipboardList size={16}/>Очередь проверки</Link>
            <Link className={location.key === "archive" ? "side-link active" : "side-link"} href="/teacher/archive"><Library size={16} />Архив</Link>
            <Link className={location.key === "originality" ? "side-link active" : "side-link"} href="/teacher/originality"><ScanSearch size={16} />Оригинальность</Link>
            {user?.account_id && <Link className={location.key === "settings" ? "side-link active" : "side-link"} href="/settings/profile">Настройки</Link>}
            {['school_admin', 'platform_admin'].includes(user?.role ?? '') && <Link className={location.key === "admin" ? "side-link active" : "side-link"} href="/admin/institutions">Учреждения</Link>}
          </nav>
        )}
        <div className="sidebar-foot"><span className="ready-dot" />{enabled ? user?.username : "ДЕМО · без входа"}</div>
      </aside>
      <main className="main-column">
        <header className="global-header">
          <div className="breadcrumbs"><span>Forma</span><span className="crumb-sep">/</span><span>{location.title}</span></div>
          {enabled && <button className="quiet-button" onClick={logout}>Выйти</button>}
        </header>
        <div className="workspace">{user?.role === "migration_pending" && <div className="notice">Существующие курсы сохранены. Для создания новых курсов требуется операторское одобрение роли и учреждения.</div>}{children}</div>
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
