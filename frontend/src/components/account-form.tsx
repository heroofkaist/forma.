"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { platformRequest } from "../lib/platform";
import { useAuth } from "./auth-provider";

type Mode = "register" | "forgot-password" | "reset-password" | "verify-email" | "profile" | "security";
const titles: Record<Mode, string> = { register: "Создать учётную запись", "forgot-password": "Восстановить доступ", "reset-password": "Новый пароль", "verify-email": "Подтвердить email", profile: "Профиль", security: "Безопасность" };
export function AccountForm({ mode }: { mode: Mode }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [registration, setRegistration] = useState<boolean | null>(null);
  const { user } = useAuth();
  const settings = mode === "profile" || mode === "security";
  useEffect(() => {
    if (mode === "register") platformRequest<{ registration_enabled: boolean }>("/api/accounts/status").then((data) => setRegistration(data.registration_enabled)).catch((cause: unknown) => setError(String(cause)));
    if (mode === "profile") platformRequest<{ email: string; display_name: string }>("/api/accounts/profile").then((data) => { setEmail(data.email); setName(data.display_name); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить профиль."));
  }, [mode]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const token = new URLSearchParams(window.location.search).get("token") ?? "";
      const path = mode === "profile" ? "profile" : mode === "security" ? "password" : mode;
      const body = mode === "register" ? { email, display_name: name, password }
        : mode === "forgot-password" ? { email }
        : mode === "profile" ? { display_name: name }
        : mode === "security" ? { current_password: currentPassword, password }
        : mode === "reset-password" ? { token, password } : { token };
      const result = await platformRequest(`/api/accounts/${path}`, body, mode === "profile" ? "PATCH" : "POST");
      setMessage(result.message); setPassword(""); setCurrentPassword("");
      if (mode === "security") window.location.assign("/login");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выполнить запрос."); }
    finally { setBusy(false); }
  }
  return <main className="auth-page"><section className="auth-card">
    <Link href={settings ? "/teacher" : "/login"} className="forma-brand auth-brand">forma<span className="brand-period">.</span></Link>
    <div className="eyebrow">{settings ? "НАСТРОЙКИ" : "УЧЁТНАЯ ЗАПИСЬ"}</div><h1>{titles[mode]}</h1>
    {mode === "register" && <p>Одна учётная запись для обучения и преподавания. Доступ к курсам определяется участием и владением.</p>}
    {mode === "register" && registration === false && <div className="notice" role="status">Регистрация пока недоступна. Администратор должен включить регистрацию и настроить отправку email.</div>}
    {settings && user?.role !== "account" ? <p>Настройки доступны для подтверждённых учётных записей. Вход с прежними реквизитами сохраняется на время перехода.</p> : <form className="auth-form" onSubmit={(event) => void submit(event)}>
      {["register", "forgot-password", "profile"].includes(mode) && <label>Email<input type="email" autoComplete="email" required maxLength={254} readOnly={mode === "profile"} value={email} onChange={(event) => setEmail(event.target.value)} /></label>}
      {["register", "profile"].includes(mode) && <label>Имя<input autoComplete="name" required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label>}
      {mode === "security" && <label>Текущий пароль<input type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>}
      {["register", "reset-password", "security"].includes(mode) && <label>Пароль · не менее 12 символов<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /></label>}
      {mode === "verify-email" && <p>Подтвердите адрес кнопкой ниже. Ссылка из письма действует один час и используется один раз.</p>}
      <button className="button primary" type="submit" disabled={busy || (mode === "register" && registration !== true)}>{busy ? "Подождите…" : mode === "verify-email" ? "Подтвердить email" : "Продолжить"}</button>
    </form>}
    {error && <div className="notice error-notice" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    {mode === "verify-email" && <form className="auth-form" onSubmit={(event) => { event.preventDefault(); setBusy(true); setError(""); void platformRequest("/api/accounts/resend-verification", { email }).then((result) => setMessage(result.message)).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось отправить письмо.")).finally(() => setBusy(false)); }}><label>Повторно отправить письмо<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><button className="button" disabled={busy}>Отправить</button></form>}
    <div className="account-links">{settings ? <><Link href="/settings/profile">Профиль</Link><Link href="/settings/security">Безопасность</Link><Link href="/student">Обучение</Link></> : <Link href="/login">Войти</Link>}</div>
  </section></main>;
}
