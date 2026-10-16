"use client";

import { FormEvent, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, ArrowUpRight, Eye, EyeOff } from "lucide-react";
import { FormaMark } from "../../components/forma-mark";
import { KnowledgeGlobe } from "../../components/knowledge-globe";
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

  return <div className="motion-login" data-paused={paused}>
    <a className="ms-skip" href="#login-form">К форме входа</a>
    <KnowledgeGlobe paused={paused} login/>
    <header className="ms-login-header"><Link href="/" className="ms-brand" aria-label="Forma · главная"><FormaMark/>forma</Link><Link className="ms-login-back" href="/"><ArrowLeft size={15} aria-hidden="true"/>На главную</Link></header>
    <main className="ms-login-layout"><section className="ms-login-story" aria-labelledby="login-story-title"><span className="ms-orbit-label"><span/>ВАШЕ УЧЕБНОЕ ПРОСТРАНСТВО</span><h2 id="login-story-title">Идеи встречаются.<br/><em>Знания растут.</em></h2><p>Курсы, работы и обратная связь.<br/>Всё начинается с вашего следующего шага.</p><span className="ms-login-coordinate" aria-hidden="true">ЧЕЛОВЕЧЕСКАЯ МЫСЛЬ × ИСКУССТВЕННЫЙ ИНТЕЛЛЕКТ</span></section>
      <section className="ms-login-panel" id="login-form" tabIndex={-1} aria-labelledby="login-title"><span className="ms-label">С ВОЗВРАЩЕНИЕМ В FORMA</span><h1 id="login-title">Продолжим?</h1><p>Войдите, чтобы открыть свои курсы и работы.</p>
        {!loading && !enabled ? <div className="ms-login-demo"><p>Локальная демо-версия доступна без входа.</p><Link className="ms-light-button" href="/assignments">Открыть демо<ArrowRight size={17} aria-hidden="true"/></Link></div> : <form onSubmit={submit} className="ms-login-form" aria-busy={submitting}>
          <div className="ms-field"><label htmlFor="login-email">Email</label><input id="login-email" name="email" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required disabled={submitting} value={username} onChange={event => setUsername(event.target.value)} placeholder="you@university.edu"/></div>
          <div className="ms-field"><div className="ms-field-heading"><label htmlFor="login-password">Пароль</label><Link href="/forgot-password">Забыли пароль?</Link></div><div className="ms-password"><input id="login-password" name="password" type={showPassword ? "text" : "password"} autoComplete="current-password" required disabled={submitting} value={password} onChange={event => setPassword(event.target.value)}/><button type="button" aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={18} aria-hidden="true"/> : <Eye size={18} aria-hidden="true"/>}</button></div></div>
          {error && <div className="ms-login-error" id="login-error" ref={errorBox} tabIndex={-1} role="alert">{error}</div>}
          <button className="ms-light-button ms-login-submit" type="submit" disabled={loading || submitting}>{loading ? "Подготавливаем вход…" : submitting ? "Входим…" : "Войти в Forma"}<ArrowRight size={17} aria-hidden="true"/></button>
          <div className="ms-login-register"><span>Впервые здесь?</span><Link href="/register">Создать аккаунт<ArrowUpRight size={14} aria-hidden="true"/></Link></div>
        </form>}
        <p className="ms-login-note">Одна учётная запись — ваше пространство преподавателя или студента.</p>
      </section></main>
    <footer className="ms-login-footer"><span>ИИ помогает. Решение принимаете вы.</span><MotionControl paused={paused} onToggle={toggle}/></footer>
  </div>;
}
