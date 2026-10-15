export function teacherRole(role?: string) { return ["teacher", "school_admin", "platform_admin", "migration_pending"].includes(role ?? ""); }
export function homeForRole(role: string) { return role === "student" ? "/student" : ["school_admin", "platform_admin"].includes(role) ? "/admin/institutions" : "/teacher"; }
export function allowedPath(role: string, path: string) {
  if (path.startsWith("/settings") || path === "/teacher-invitation") return true;
  if (role === "student") return path.startsWith("/student");
  if (path.startsWith("/student")) return false;
  if (path.startsWith("/admin")) return ["school_admin", "platform_admin"].includes(role);
  return teacherRole(role);
}
export function locationForPath(path: string) {
  if (path.startsWith("/teacher/archive")) return { key: "archive", title: "Архив" };
  if (path.includes("/originality")) return { key: "originality", title: "Оригинальность" };
  if (path.startsWith("/settings")) return { key: "settings", title: "Настройки" };
  if (path.startsWith("/admin")) return { key: "admin", title: "Учреждения" };
  if (path.includes("/review") || path.includes("/submissions")) return { key: "review", title: "Проверка работ" };
  if (path.startsWith("/teacher")) return { key: "courses", title: "Курсы" };
  return { key: "assignments", title: path.includes("/template") ? "Дополнительный шаблон" : path.includes("/results") ? "Результаты" : "Задания" };
}

export function publicPath(path: string, development = false) {
  return ["/", "/login", "/register", "/forgot-password", "/reset-password", "/verify-email", "/guardian-consent", "/teacher-invitation"].includes(path)
    || (development && path === "/design-preview");
}
