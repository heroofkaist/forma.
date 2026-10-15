"use client";
import { useId, useState, type CSSProperties, type FormEvent } from "react";
import { platformRequest } from "../lib/platform";
import { ageBand, ageLabel } from "../lib/registration-age";
import { GuardianRequest } from "./guardian-request";

export function AgeScreen({ onEligible, guardianEnabled = false }: { onEligible: (token: string) => void; guardianEnabled?: boolean }) {
  const id = useId();
  const [age, setAge] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [guardianToken, setGuardianToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const band = ageBand(age);
  function choose(value: string) { setAge(value); setConfirmed(false); setError(""); }
  async function check(event: FormEvent) {
    event.preventDefault(); if (!band || !confirmed || busy) return;
    setBusy(true); setError("");
    try {
      const result = await platformRequest<{ eligible: boolean; next_step?: string; age_check_token: string }>("/api/accounts/age-check", { age_band: band });
      if (result.eligible) onEligible(result.age_check_token);
      else if (result.next_step === "guardian") setGuardianToken(result.age_check_token);
      else setBlocked(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось проверить возраст. Попробуйте снова."); }
    finally { setBusy(false); }
  }
  if (guardianToken) return guardianEnabled ? <GuardianRequest ageToken={guardianToken} onEligible={onEligible}/> : <div className="age-result" role="status"><h2>Нужно согласие родителя</h2><p>Для 13–17 лет предусмотрено подтверждение родителем по email. Оно станет доступно после настройки уведомления об обработке данных и отправки писем.</p><LinkToLogin/></div>;
  if (blocked) return <div className="age-result" role="status"><h2>Доступ через школу</h2><p>До 13 лет самостоятельная регистрация недоступна. Родителю или законному представителю нужно обратиться в ваше учебное учреждение.</p><LinkToLogin/></div>;
  return <form className="auth-form age-screen" onSubmit={(event) => void check(event)} data-private="true">
    <div><div className="eyebrow">ШАГ 1 / ВОЗРАСТ</div><p id={`${id}-hint`}>Перед началом укажите свой возраст. Дата рождения не нужна.</p></div>
    <div className="age-picker">
      <output className="age-value" htmlFor={`${id}-range ${id}-number`} aria-live="polite">{ageLabel(age)}</output>
      <label className="rw-sr-only" htmlFor={`${id}-range`}>Выберите свой возраст ползунком</label>
      <input id={`${id}-range`} className="age-range" type="range" min={0} max={80} step={1} value={Math.min(Number(age) || 0, 80)} aria-valuetext={age ? Number(age) >= 80 ? "80 лет и старше; точный возраст можно ввести ниже" : ageLabel(age) : "Возраст не выбран"} aria-describedby={`${id}-hint`} disabled={busy} onChange={event => choose(event.target.value)} style={{"--age-progress": `${Math.min(Number(age) || 0,80)/80*100}%`} as CSSProperties}/>
      <div className="age-scale" aria-hidden="true"><span>0</span><span>20</span><span>40</span><span>60</span><span>80+</span></div>
      <label className="age-exact" htmlFor={`${id}-number`}>Или введите возраст<input id={`${id}-number`} type="number" inputMode="numeric" min={0} max={120} step={1} value={age} placeholder="—" disabled={busy} onChange={event => choose(event.target.value)} /></label>
    </div>
    <label className="age-confirmation"><input type="checkbox" required checked={confirmed} disabled={!band || busy} onChange={event => setConfirmed(event.target.checked)}/><span>Подтверждаю, что указал(а) свой возраст верно.</span></label>
    <button className="button primary" type="submit" disabled={busy || !band || !confirmed}>{busy ? "Проверяем…" : "Продолжить"}</button>
    {error && <p className="notice error-notice" role="alert">{error}</p>}
  </form>;
}
function LinkToLogin() { return <a className="quiet-button" href="/login">Вернуться ко входу</a>; }
