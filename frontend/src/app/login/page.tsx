"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GraduationCap } from "lucide-react";
import { useAuth } from "../../components/auth-provider";

export default function LoginPage() {
  const { enabled, loading, login } = useAuth();
  const router = useRouter();
  const [role, setRole] = useState("student");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(role, username.trim(), password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next?.startsWith("/") && !next.startsWith("//") ? next : role === "teacher" ? "/" : "/student");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось войти.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <Link href="/" className="forma-brand auth-brand">
          <span className="brand-mark"><GraduationCap size={17} /></span>
          forma<span className="brand-period">.</span>
        </Link>
        <div className="eyebrow">БЕЗОПАСНЫЙ ДОСТУП</div>
        <h1>Войти в Forma</h1>
        {!loading && !enabled ? (
          <div className="auth-demo">
            <p>Для локальной демо-версии вход не требуется.</p>
            <Link className="button primary" href="/">Продолжить в демо</Link>
          </div>
        ) : (
          <form onSubmit={submit} className="auth-form">
            <label>Тип учетной записи
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="student">Ученик</option>
                <option value="teacher">Учитель</option>
              </select>
            </label>
            <label>{role === "student" ? "ID ученика" : "Имя пользователя"}
              <input autoComplete="username" required value={username} onChange={(event) => setUsername(event.target.value)} />
            </label>
            <label>Пароль
              <input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} />
            </label>
            {error && <div className="notice error-notice" role="alert">{error}</div>}
            <button className="button primary" type="submit" disabled={loading || submitting}>
              {submitting ? "Входим…" : "Войти"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
