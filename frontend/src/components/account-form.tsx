"use client";
import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { platformRequest, PlatformError } from "../lib/platform";
import { useAuth } from "./auth-provider";
import { AuthStudy } from "./auth-study";
import { FormaMark } from "./forma-mark";
import { AgeScreen } from "./age-screen";
import { LearningScene } from "./learning-scene";
import { SkyBackdrop } from "./sky-backdrop";

type Mode = "register" | "forgot-password" | "reset-password" | "verify-email" | "profile" | "security";
const titles: Record<Mode, string> = { register: "Создать аккаунт", "forgot-password": "Восстановить доступ", "reset-password": "Новый пароль", "verify-email": "Подтвердить email", profile: "Профиль", security: "Безопасность" };
export function AccountForm({ mode }: { mode: Mode }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [registration, setRegistration] = useState<boolean | null>(null);
  const [ageToken, setAgeToken] = useState("");
  const [guardianEnabled, setGuardianEnabled] = useState(false);
  const { user } = useAuth();
  const settings = mode === "profile" || mode === "security";
  useEffect(() => {
    if (mode === "register") platformRequest<{ registration_enabled: boolean; guardian_registration_enabled?: boolean }>("/api/accounts/status").then((data) => { setRegistration(data.registration_enabled); setGuardianEnabled(data.guardian_registration_enabled === true); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось проверить доступность регистрации."));
    if (mode === "profile") platformRequest<{ email: string; display_name: string }>("/api/accounts/profile").then((data) => { setEmail(data.email); setName(data.display_name); }).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось загрузить профиль."));
  }, [mode]);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      const token = new URLSearchParams(window.location.search).get("token") ?? "";
      const path = mode === "profile" ? "profile" : mode === "security" ? "password" : mode;
      const body = mode === "register" ? { email, display_name: name, password, age_check_token: ageToken }
        : mode === "forgot-password" ? { email }
        : mode === "profile" ? { display_name: name }
        : mode === "security" ? { current_password: currentPassword, password }
        : mode === "reset-password" ? { token, password } : { token };
      const result = await platformRequest(`/api/accounts/${path}`, body, mode === "profile" ? "PATCH" : "POST");
      setMessage(({ register: "Если адрес доступен для регистрации, на него отправлено письмо для подтверждения.", "forgot-password": "Если учётная запись существует, письмо для восстановления отправлено.", "reset-password": "Пароль изменён. Войдите с новым паролем.", "verify-email": "Адрес электронной почты подтверждён.", profile: "Профиль сохранён.", security: "Пароль изменён. Войдите снова." })[mode]); setPassword(""); setCurrentPassword("");
      if (mode === "security") window.location.assign("/login");
    } catch (cause) {
      if (mode === "register" && cause instanceof PlatformError && ["Complete the age check before registration.", "Guardian approval is required or has expired."].includes(String(cause.detail))) {
        setAgeToken(""); setPassword(""); setError("Проверка возраста или согласия больше не действует. Подтвердите возраст ещё раз; имя и email сохранены на этой странице.");
      } else setError(cause instanceof Error ? cause.message : "Не удалось выполнить запрос.");
    }
    finally { setBusy(false); }
  }
  const accountPanel = <section className={mode === "register" ? "cf-login-panel cf-register-panel" : "auth-card"}>
    <Link href={settings ? "/teacher" : "/login"} className="forma-brand auth-brand"><FormaMark/>forma<span className="brand-period">.</span></Link>
    <div className="eyebrow">{settings ? "НАСТРОЙКИ" : "УЧЁТНАЯ ЗАПИСЬ"}</div><h1>{titles[mode]}</h1>
    {mode === "register" && <p>Для студентов и школьников. Преподаватели получают доступ по приглашению учреждения.</p>}
    {mode === "register" && registration === false && <div className="notice" role="status">Регистрация пока недоступна. Обратитесь к администратору вашего учреждения.</div>}
    {mode === "register" && registration === null && !error && <p role="status">Проверяем доступность регистрации…</p>}
    {mode === "register" && registration === true && !ageToken && <AgeScreen onEligible={setAgeToken} guardianEnabled={guardianEnabled}/>}
    {mode === "register" && (registration !== true || !ageToken) ? null : settings && !user?.account_id ? <p>Для изменения настроек войдите в подтверждённую учётную запись через email.</p> : <form className="auth-form" onSubmit={(event) => void submit(event)}>
      {["register", "forgot-password", "profile"].includes(mode) && <label>Email<input type="email" autoComplete="email" required maxLength={254} readOnly={mode === "profile"} value={email} onChange={(event) => setEmail(event.target.value)} /></label>}
      {["register", "profile"].includes(mode) && <label>Имя<input autoComplete="name" required maxLength={200} value={name} onChange={(event) => setName(event.target.value)} /></label>}
      {mode === "security" && <label>Текущий пароль<input type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>}
      {["register", "reset-password", "security"].includes(mode) && <label>Пароль · не менее 12 символов<input type="password" autoComplete="new-password" required minLength={12} maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} /></label>}
      {mode === "verify-email" && <p>Подтвердите адрес кнопкой ниже. Ссылка из письма действует один час и используется один раз.</p>}
      <button className="button primary" type="submit" disabled={busy || (mode === "register" && registration !== true)}>{busy ? "Подождите…" : mode === "verify-email" ? "Подтвердить email" : "Продолжить"}</button>
      {mode === "register" && <button className="quiet-button" type="button" disabled={busy} onClick={() => setAgeToken("")}>Проверить возраст снова</button>}
    </form>}
    {error && <div className="notice error-notice" role="alert">{error}</div>}{message && <div className="notice" role="status">{message}</div>}
    {mode === "verify-email" && <form className="auth-form" onSubmit={(event) => { event.preventDefault(); setBusy(true); setError(""); void platformRequest("/api/accounts/resend-verification", { email }).then(() => setMessage("Если адрес требует подтверждения, письмо отправлено.")).catch((cause: unknown) => setError(cause instanceof Error ? cause.message : "Не удалось отправить письмо.")).finally(() => setBusy(false)); }}><label>Повторно отправить письмо<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label><button className="button" disabled={busy}>Отправить</button></form>}
    <div className="account-links">{settings ? <><Link href="/settings/profile">Профиль</Link><Link href="/settings/security">Безопасность</Link><Link href="/student">Обучение</Link></> : mode === "register" ? <span>Уже есть аккаунт? <Link href="/login">Войти</Link></span> : <Link href="/login">Войти</Link>}</div>
  </section>;
  if (mode === "register") return <div className="cf-login cf-register">
    <a className="cf-skip" href="#register-panel">К форме регистрации</a>
    <SkyBackdrop/>
    <header className="cf-login-header"><Link href="/" className="cf-brand" aria-label="Forma, главная"><FormaMark/>forma</Link><Link className="cf-login-back" href="/"><ArrowLeft size={15} aria-hidden="true"/>На главную</Link></header>
    <main className="cf-login-layout">
      <section className="cf-login-story" aria-label="О Forma">
        <div className="cf-login-scene-copy"><h2>Учитесь в своём темпе</h2><p>Задания, обратная связь и оценки собраны в одном месте.</p></div>
        <LearningScene compact paused/>
      </section>
      <div id="register-panel" tabIndex={-1}>{accountPanel}</div>
    </main>
  </div>;
  return <main className="auth-page"><AuthStudy/>{accountPanel}</main>;
}
