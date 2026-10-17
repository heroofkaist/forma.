"use client";

import { FormEvent, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, ArrowUpRight, Eye, EyeOff } from "lucide-react";
import { FormaMark } from "../../components/forma-mark";
import { LearningScene } from "../../components/learning-scene";
import { SkyBackdrop } from "../../components/sky-backdrop";
import { MotionControl, useSceneMotion } from "../../components/motion-control";
import { homeForRole, allowedPath } from "../../lib/navigation";
import { useAuth } from "../../components/auth-provider";

export default function LoginPage() {
  const { enabled, loading, login } = useAuth();
  const { paused, toggle } = useSceneMotion();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const sending = useRef(false);
  const errorBox = useRef<HTMLDivElement>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (sending.current) return;
    sending.current = true; setSubmitting(true); setError("");
    try {
      const identityRole = await login("student", username.trim(), password);
      const next = new URLSearchParams(window.location.search).get("next");
      router.replace(next?.startsWith("/") && !next.startsWith("//") && allowedPath(identityRole, next) ? next : homeForRole(identityRole));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось войти. Попробуйте ещё раз.");
      requestAnimationFrame(() => errorBox.current?.focus());
    } finally { sending.current = false; setSubmitting(false); }
  }

  return <div className="cf-login" data-paused={paused}>
    <a className="cf-skip" href="#login-form">К форме входа</a>
    <SkyBackdrop/>
    <header className="cf-login-header"><Link href="/" className="cf-brand" aria-label="Forma, главная"><FormaMark/>forma</Link><Link className="cf-login-back" href="/"><ArrowLeft size={15} aria-hidden="true"/>На главную</Link></header>
    <main className="cf-login-layout"><section className="cf-login-story" aria-label="Пример проверки"><div className="cf-login-scene-copy"><h2>Все работы под рукой</h2><p>Проверяйте по критериям и оставляйте понятные комментарии.</p></div><LearningScene paused={paused} compact/></section>
      <section className="cf-login-panel" id="login-form" tabIndex={-1} aria-labelledby="login-title"><h1 id="login-title">Войти в Forma</h1><p>Откройте свои курсы, работы и оценки.</p>
        {!loading && !enabled ? <div className="cf-login-demo"><p>Локальная демо-версия доступна без входа.</p><Link className="cf-button cf-button-blue" href="/assignments">Открыть демо<ArrowRight size={17} aria-hidden="true"/></Link></div> : <form onSubmit={submit} className="cf-login-form" aria-busy={submitting}>
          <div className="cf-field"><label htmlFor="login-email">Email</label><input id="login-email" name="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required disabled={submitting} value={username} onChange={event => setUsername(event.target.value)} placeholder="you@university.edu"/></div>
          <div className="cf-field"><div className="cf-field-heading"><label htmlFor="login-password">Пароль</label><Link href="/forgot-password">Забыли пароль?</Link></div><div className="cf-password"><input id="login-password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required disabled={submitting} value={password} onChange={event => setPassword(event.target.value)}/><button type="button" aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={18} aria-hidden="true"/> : <Eye size={18} aria-hidden="true"/>}</button></div></div>
          {error && <div className="cf-login-error" id="login-error" ref={errorBox} tabIndex={-1} role="alert">{error}</div>}
          <button className="cf-button cf-button-blue cf-login-submit" type="submit" disabled={loading || submitting}>{loading ? "Подготавливаем вход…" : submitting ? "Входим…" : "Войти в Forma"}<ArrowRight size={17} aria-hidden="true"/></button>
          <div className="cf-login-register"><span>Впервые здесь?</span><Link href="/register">Создать аккаунт<ArrowUpRight size={14} aria-hidden="true"/></Link></div>
        </form>}
        <p className="cf-login-note">Используйте свою учётную запись преподавателя или студента.</p>
      </section></main>
    <footer className="cf-login-footer"><span>Курсы, работы и обратная связь</span><MotionControl paused={paused} onToggle={toggle}/></footer>
  </div>;
}
