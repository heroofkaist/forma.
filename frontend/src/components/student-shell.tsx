"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { BookOpen, CalendarDays } from "lucide-react";
import { FormaMark } from "./forma-mark";
import { useAuth } from "./auth-provider";

export function StudentShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { enabled, user, logout } = useAuth();
  useEffect(() => { document.title = `${pathname === "/student/grades" ? "Мои оценки" : pathname.includes("/assignments/") ? "Задание" : "Мои курсы"} · Forma`; }, [pathname]);
  return <div className="student-frame">
    <a className="skip-link" href="#student-content">К содержанию</a><header className="student-header">
      <Link href="/student" className="student-brand"><FormaMark/>forma</Link>
      <nav aria-label="Пространство студента">
        <Link className={pathname === "/student" || pathname.startsWith("/student/courses") ? "active" : ""} href="/student"><BookOpen size={15} />Мои курсы</Link>
        <Link className={pathname === "/student/grades" ? "active" : ""} href="/student/grades"><CalendarDays size={15} />Оценки</Link>
      </nav>
      <div className="student-user"><span className="student-demo-pill">{enabled ? "СТУДЕНТ" : "ДЕМО · студент"}</span><span className="student-avatar">S</span><span>{user?.username ?? "Студент"}</span>{enabled ? <><Link href="/student/join" className="student-role-link">Вступить в курс</Link><button className="student-role-link" onClick={logout}>Выйти</button></> : null}</div>
    </header>
    <main className="student-content" id="student-content" tabIndex={-1}>{children}<p className="privacy-note">{enabled ? "Здесь доступны ваши работы и опубликованные преподавателем оценки." : "Демонстрационный режим с вымышленными данными. Реальные работы доступны только после входа."}</p></main>
  </div>;
}
