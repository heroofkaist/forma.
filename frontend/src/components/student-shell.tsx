"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, CalendarDays, GraduationCap } from "lucide-react";

export function StudentShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return <div className="student-frame">
    <header className="student-header">
      <Link href="/student" className="student-brand"><span><GraduationCap size={17} /></span>forma</Link>
      <nav>
        <Link className={pathname === "/student" || pathname.startsWith("/student/courses") ? "active" : ""} href="/student"><BookOpen size={15} />Мои курсы</Link>
        <Link className={pathname === "/student/grades" ? "active" : ""} href="/student/grades"><CalendarDays size={15} />Оценки</Link>
      </nav>
      <div className="student-user"><span className="student-demo-pill">ДЕМО · студент</span><span className="student-avatar">S</span><span>Студент</span><Link href="/" className="student-role-link">Вид преподавателя</Link></div>
    </header>
    <main className="student-content">{children}<p className="privacy-note">Демонстрационный режим с вымышленными данными. Переключение вида не является входом в систему или проверкой прав.</p></main>
  </div>;
}
