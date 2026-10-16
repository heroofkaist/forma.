"use client";

import Link from "next/link";

export default function SubmissionsError({ reset }: { reset: () => void }) {
  return <main className="assignment-workspace">
    <h1>Не удалось открыть работы</h1>
    <p role="alert">Попробуйте загрузить страницу ещё раз. Если ошибка повторится, вернитесь к списку курсов.</p>
    <button className="button primary" onClick={reset}>Повторить</button>
    <Link className="button" href="/teacher">К курсам</Link>
  </main>;
}
