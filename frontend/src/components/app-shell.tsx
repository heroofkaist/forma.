"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { BookOpen, ClipboardCheck, Files, Library, ScanSearch, Settings, Building2, LogOut } from "lucide-react";
import { teacherRole, locationForPath } from "../lib/navigation";
import { statusLabel } from "../lib/presentation";
import { FormaMark } from "./forma-mark";
import { useAuth } from "./auth-provider";

const destinations = [
  { key: "courses", href: "/teacher", label: "Мои курсы", icon: BookOpen },
  { key: "review", href: "/teacher/review", label: "Проверка работ", icon: ClipboardCheck },
  { key: "assignments", href: "/assignments", label: "Все задания", icon: Files },
  { key: "archive", href: "/teacher/archive", label: "Архив работ", icon: Library },
  { key: "originality", href: "/teacher/originality", label: "Совпадения", icon: ScanSearch },
];

export function AppShell({ children, workspaceClassName = "" }: { children: React.ReactNode; workspaceClassName?: string }) {
  const location = locationForPath(usePathname());
  const { enabled, user, logout } = useAuth();
  const name = user?.username || "Демо-пространство";
  useEffect(() => { document.title = `${location.title} · Forma`; }, [location.title]);
  return <div className={`app-frame ${workspaceClassName === "workspace-review" ? "review-frame" : ""}`}>
    <a className="skip-link" href="#main-content">К содержанию</a>
    <aside className="sidebar">
      <Link href="/teacher" className="forma-brand" aria-label="Forma · мои курсы"><FormaMark/>forma<span className="brand-period">.</span></Link>
      <div className="workspace-label">Пространство преподавателя</div>
      {(!enabled || teacherRole(user?.role)) && <nav className="side-nav" aria-label="Рабочее пространство">
        {destinations.map(({ key, href, label, icon: Icon }) => <Link key={key} className={`side-link${location.key === key ? " active" : ""}`} aria-current={location.key === key ? "page" : undefined} href={href}><Icon size={19} aria-hidden="true"/>{label}</Link>)}
        {user?.account_id && <Link className={`side-link side-settings${location.key === "settings" ? " active" : ""}`} aria-current={location.key === "settings" ? "page" : undefined} href="/settings/profile"><Settings size={19} aria-hidden="true"/>Настройки</Link>}
        {["school_admin", "platform_admin"].includes(user?.role ?? "") && <Link className={`side-link${location.key === "admin" ? " active" : ""}`} aria-current={location.key === "admin" ? "page" : undefined} href="/admin/institutions"><Building2 size={19} aria-hidden="true"/>Учреждения</Link>}
      </nav>}
      <div className="sidebar-context"><span>Вы принимаете решение</span><p>ИИ помогает с разбором.<br/>Итоговая оценка — за вами.</p></div>
      <div className="sidebar-foot"><span className="account-avatar" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span><div><strong>{name}</strong><span>{enabled ? "Преподаватель" : "Вымышленные данные"}</span></div></div>
    </aside>
    <div className="main-column">
      <header className="global-header"><nav className="breadcrumbs" aria-label="Текущий раздел"><Link href="/teacher">Рабочее пространство</Link><span className="crumb-sep" aria-hidden="true">/</span><span aria-current="page">{location.title}</span></nav>{enabled && <button className="quiet-button" onClick={logout}><LogOut size={15} aria-hidden="true"/>Выйти</button>}</header>
      <main className={`workspace ${workspaceClassName}`} id="main-content" tabIndex={-1}>{user?.role === "migration_pending" && <div className="notice">Ваши курсы сохранены. Для создания новых курсов администратор должен подтвердить роль и учреждение.</div>}{children}</main>
    </div>
  </div>;
}

export function StatusLabel({ status }: { status: string }) {
  return <span className={`status-label status-${status}`}>{statusLabel(status)}</span>;
}
