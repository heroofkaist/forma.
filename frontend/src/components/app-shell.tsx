"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpenCheck, ClipboardList, Library, ScanSearch } from "lucide-react";
import { teacherRole, locationForPath } from "../lib/navigation";
import { statusLabel } from "../lib/presentation";
import { FormaMark } from "./forma-mark";
import { useAuth } from "./auth-provider";

export function AppShell({ children, workspaceClassName = "" }: { children: React.ReactNode; workspaceClassName?: string }) {
  const pathname = usePathname();
  const location = locationForPath(pathname);
  const { enabled, user, logout } = useAuth();
  return (
    <div className={`app-frame ${workspaceClassName === "workspace-review" ? "review-frame" : ""}`}>
      <aside className="sidebar">
        <Link href="/" className="forma-brand"><FormaMark/>forma<span className="brand-period">.</span></Link>
        <div className="workspace-label">БЮРО / РАБОЧИЙ ИНДЕКС</div>
        {(!enabled || teacherRole(user?.role)) && (
          <nav className="side-nav" aria-label="Рабочее пространство">
            <Link className={location.key === "assignments" ? "side-link active" : "side-link"} href="/assignments"><ClipboardList size={16} />Задания<span className="nav-index" aria-hidden="true">01</span></Link>
            <Link className={location.key === "courses" ? "side-link active" : "side-link"} href="/teacher"><BookOpenCheck size={16} />Курсы<span className="nav-index" aria-hidden="true">02</span></Link>
            <Link className={location.key === "review" ? "side-link active" : "side-link"} href="/teacher/review"><ClipboardList size={16}/>Очередь проверки<span className="nav-index" aria-hidden="true">03</span></Link>
            <Link className={location.key === "archive" ? "side-link active" : "side-link"} href="/teacher/archive"><Library size={16} />Архив<span className="nav-index" aria-hidden="true">04</span></Link>
            <Link className={location.key === "originality" ? "side-link active" : "side-link"} href="/teacher/originality"><ScanSearch size={16} />Оригинальность<span className="nav-index" aria-hidden="true">05</span></Link>
            {user?.account_id && <Link className={location.key === "settings" ? "side-link active" : "side-link"} href="/settings/profile">Настройки<span className="nav-index" aria-hidden="true">06</span></Link>}
            {['school_admin', 'platform_admin'].includes(user?.role ?? '') && <Link className={location.key === "admin" ? "side-link active" : "side-link"} href="/admin/institutions">Учреждения<span className="nav-index" aria-hidden="true">07</span></Link>}
          </nav>
        )}
        <div className="sidebar-imprint" aria-hidden="true"><span>↳</span>Внимание<br/>к деталям.</div>
        <div className="sidebar-foot"><span className="ready-dot" />{enabled ? user?.username : "ДЕМО · без входа"}</div>
      </aside>
      <a className="skip-link" href="#main-content">К содержанию</a><main className="main-column" id="main-content">
        <header className="global-header">
          <div className="breadcrumbs"><span>Forma</span><span className="crumb-sep">/</span><span>{location.title}</span></div>
          {enabled && <button className="quiet-button" onClick={logout}>Выйти</button>}
        </header>
        <div className={`workspace ${workspaceClassName}`}>{user?.role === "migration_pending" && <div className="notice">Существующие курсы сохранены. Для создания новых курсов требуется операторское одобрение роли и учреждения.</div>}{children}</div>
      </main>
    </div>
  );
}

export function StatusLabel({ status }: { status: string }) {
  return <span className={`status-label status-${status}`}>{statusLabel(status)}</span>;
}
