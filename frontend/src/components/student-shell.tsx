"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, CalendarDays, GraduationCap } from "lucide-react";
import { useAuth } from "./auth-provider";

export function StudentShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { enabled, user, logout } = useAuth();
  return <div className="student-frame">
    <header className="student-header">
      <Link href="/student" className="student-brand"><span><GraduationCap size={17} /></span>forma</Link>
      <nav>
        <Link className={pathname === "/student" || pathname.startsWith("/student/courses") ? "active" : ""} href="/student"><BookOpen size={15} />Мои курсы</Link>
        <Link className={pathname === "/student/grades" ? "active" : ""} href="/student/grades"><CalendarDays size={15} />Оценки</Link>
      </nav>
      <div className="student-user"><span className="student-demo-pill">{enabled ? "УЧЕНИК" : "ДЕМО · студент"}</span><span className="student-avatar">S</span><span>{user?.username ?? "Студент"}</span>{enabled ? <><Link href="/student/join" className="student-role-link">Вступить в курс</Link><button className="student-role-link" onClick={logout}>Выйти</button></> : null}</div>
    </header>
    <main className="student-content">{children}<p className="privacy-note">{enabled ? "Ваши задания и оценки доступны только вашей учётной записи." : "Демонстрационный режим с вымышленными данными. Переключение student/teacher не является входом в систему или проверкой прав."}</p></main>
  </div>;
}
