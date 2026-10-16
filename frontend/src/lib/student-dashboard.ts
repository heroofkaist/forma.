import type { AcademicAssignment, Course } from "./academic";

export type WorkFilter = "all" | "todo" | "submitted" | "graded";
export const workFilters: { value: WorkFilter; label: string }[] = [
  { value: "all", label: "Все" }, { value: "todo", label: "Нужно сдать" },
  { value: "submitted", label: "На проверке" }, { value: "graded", label: "Оценено" },
];
export function workState(item: AcademicAssignment): Exclude<WorkFilter, "all"> {
  if (item.published_at || item.submission_status === "graded") return "graded";
  return item.latest_submission || item.submission_status === "submitted" ? "submitted" : "todo";
}
export function dueTime(item: AcademicAssignment) {
  const value = item.due_at ? Date.parse(item.due_at) : NaN;
  return Number.isFinite(value) ? value : Infinity;
}
export function dashboardWork(items: AcademicAssignment[], filter: WorkFilter) {
  return items.filter(item => filter === "all" || workState(item) === filter)
    .sort((a, b) => {
      const first = dueTime(a), second = dueTime(b);
      return first === second ? a.title.localeCompare(b.title, "ru") : first < second ? -1 : 1;
    });
}
export function searchCourses(courses: Course[], search: string) {
  const query = search.trim().toLocaleLowerCase("ru");
  return courses.flatMap(course => course.offerings.map(offering => ({ course, offering })))
    .filter(({course, offering}) => !query || [course.name, course.code, offering.instructor ?? course.instructor, offering.term, offering.academic_year].join(" ").toLocaleLowerCase("ru").includes(query));
}
export function taskCount(count: number) {
  const remainder = count % 100, last = count % 10;
  const noun = remainder >= 11 && remainder <= 14 ? "заданий" : last === 1 ? "задание" : last >= 2 && last <= 4 ? "задания" : "заданий";
  return `${count} ${noun}`;
}
