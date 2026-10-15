"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AssignmentCreateForm } from "../../../components/assignment-create-form";
import { AppShell } from "../../../components/app-shell";
import { academicApi, type Offering } from "../../../lib/academic";

export default function NewAssignmentPage() {
  const router = useRouter();
  const [offerings, setOfferings] = useState<Offering[]>([]);
  const [offeringId, setOfferingId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => { academicApi.offerings().then((items) => { setOfferings(items); setOfferingId(items[0]?.id ?? ""); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить курсы.")).finally(() => setLoading(false)); }, []);
  return <AppShell><section className="page-heading compact-heading"><div><h1>Создать задание</h1><p>Студенты отправляют собственный многостраничный PDF. Бланк, области ответов и эталонное решение не требуются.</p></div></section>
    {error && <div className="notice error-notice" role="alert">{error}</div>}
    {loading ? <p>Загружаем курсы…</p> : !offerings.length ? <p>Сначала <Link href="/teacher/courses/new">создайте курс</Link>.</p> : <div className="auth-form">
      <label>Учебный поток<select required value={offeringId} onChange={(event) => setOfferingId(event.target.value)}>{offerings.map((item) => <option key={item.id} value={item.id}>{item.course_name ?? item.name} · {item.term} {item.academic_year} · {item.section}</option>)}</select></label>
      <AssignmentCreateForm key={offeringId} offeringId={offeringId} onCreated={id => router.push(`/teacher/assignments/${id}/submissions`)}/>
    </div>}

  </AppShell>;
}
