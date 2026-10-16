import { CourseEnrollment } from "../../../components/course-enrollment";
import { StudentShell } from "../../../components/student-shell";

export default function JoinPage() {
  return <StudentShell><div className="student-page-title"><div><div className="eyebrow">ЗАПИСЬ НА КУРС</div><h1>Вступить в курс</h1><p>Введите код, полученный от преподавателя, и проверьте сведения курса.</p></div></div><CourseEnrollment/></StudentShell>;
}
