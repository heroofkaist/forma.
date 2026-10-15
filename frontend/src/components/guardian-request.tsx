"use client";
import { useEffect, useState, useCallback } from "react";
import { platformRequest } from "../lib/platform";

type Status = {status: string; request_code: string | null};
export function GuardianRequest({ageToken, onEligible}: {ageToken: string; onEligible: (token: string) => void}) {
  const [email, setEmail] = useState(""); const [code, setCode] = useState("");
  const [finished, setFinished] = useState("");
  const [waiting, setWaiting] = useState(false); const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(""); const [error, setError] = useState("");
  const check = useCallback(async () => {
    const result = await platformRequest<Status>("/api/accounts/guardian-consent/status", {age_check_token: ageToken});
    if (result.status === "approved") { onEligible(ageToken); return; }
    if (result.status === "pending") { setCode(result.request_code ?? ""); setWaiting(true); return; }
    if (result.status === "expired") { setWaiting(false); setMessage("Срок ссылки истёк. Можно отправить новое письмо родителю."); }
    if (result.status === "declined") { setWaiting(false); setFinished("Родитель не дал согласие. Регистрация недоступна."); }
    if (result.status === "consumed") { setWaiting(false); setFinished("Учётная запись уже создана. Подтвердите email ребёнка по письму, затем войдите."); }
  }, [ageToken, onEligible]);
  useEffect(() => { void check().catch(() => setError("Не удалось загрузить статус согласия. Попробуйте обновить страницу.")); }, [check]);
  useEffect(() => { if (!waiting) return; const timer=window.setInterval(() => { void check().catch(() => setError("Не удалось обновить статус. Нажмите «Проверить согласие».")); },10000); return () => window.clearInterval(timer); }, [waiting, check]);
  async function send(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try { const result=await platformRequest<{request_code: string; status: string}>("/api/accounts/guardian-consent/request", {email, age_check_token: ageToken}); setCode(result.request_code);
      if (result.status === "approved") onEligible(ageToken);
      else if (result.status === "declined") setFinished("Родитель не дал согласие. Регистрация недоступна.");
      else if (result.status === "consumed") setFinished("Учётная запись уже создана. Подтвердите email ребёнка по письму, затем войдите.");
      else setWaiting(true); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось отправить письмо."); }
    finally { setBusy(false); }
  }
  return <section className="auth-form guardian-request"><div className="eyebrow">ШАГ 2 / СОГЛАСИЕ РОДИТЕЛЯ</div><h2>Продолжим вместе с родителем</h2><p>Для регистрации в 13–17 лет нужно подтверждение родителя или законного представителя. Ваше имя, email и пароль вводятся после его согласия.</p>
    {finished ? <p role="status">{finished} <a href="/login">Ко входу →</a></p> : !waiting ? <form className="auth-form" onSubmit={event => void send(event)}><label>Email родителя<input type="email" disabled={busy} autoComplete="off" required maxLength={254} value={email} onChange={event => setEmail(event.target.value)} placeholder="parent@example.com"/></label><button className="button primary" disabled={busy}>{busy ? "Отправляем…" : "Отправить ссылку родителю"}</button></form> : <>
      <div className="age-request-code"><span>Код запроса для родителя</span><strong>{code}</strong></div><p>Письмо со ссылкой поставлено в очередь отправки. Попросите родителя сверить код, прочитать уведомление и подтвердить согласие. Ссылка действует один час.</p>
      <button className="button primary" disabled={busy} onClick={() => {setBusy(true); setError(""); void check().catch(cause => setError(cause instanceof Error ? cause.message : "Не удалось проверить согласие.")).finally(() => setBusy(false));}}>Проверить согласие</button>
      <button className="quiet-button" disabled={busy} onClick={() => {setWaiting(false);setError("");}}>Изменить email или отправить снова</button>
    </>}
    {message && <p role="status">{message}</p>}{error && <p className="notice error-notice" role="alert">{error}</p>}
  </section>;
}
