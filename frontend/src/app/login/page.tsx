"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormaMark } from "../../components/forma-mark";
import { AuthStudy } from "../../components/auth-study";
import { homeForRole, allowedPath } from "../../lib/navigation";
import { useAuth } from "../../components/auth-provider";

export default function LoginPage() {
  const { enabled, loading, login } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const identityRole = await login("student", username.trim(), password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next?.startsWith("/") && !next.startsWith("//") && allowedPath(identityRole, next) ? next : homeForRole(identityRole));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось войти.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page"><AuthStudy/>
      <section className="auth-card">
        <Link href="/" className="forma-brand auth-brand">
          <FormaMark/>
          forma<span className="brand-period">.</span>
        </Link>
        <div className="eyebrow">ВХОД В FORMA</div>
        <h1>Войти в Forma<span className="ink-dot">.</span></h1><p>Войдите, чтобы открыть курсы, задания и оценки.</p>
        {!loading && !enabled ? (
          <div className="auth-demo">
            <p>Для локальной демо-версии вход не требуется.</p>
            <Link className="button primary" href="/assignments">Продолжить в демо</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="auth-form">
            <label>Email
              <input type="email" autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label>Пароль
              <input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
            </label>
            {error && <div className="notice error-notice" role="alert">{error}</div>}
            <button className="button primary" type="submit" disabled={loading || submitting}>
              {submitting ? "Входим…" : "Войти"}
            </button>
            <Link href="/register">Создать учётную запись</Link>
            <Link href="/forgot-password">Забыли пароль?</Link>
          </form>
        )}
      </section>
    </main>
  );
}
