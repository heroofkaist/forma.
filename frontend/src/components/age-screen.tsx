"use client";
import { useState, type FormEvent } from "react";
import { platformRequest } from "../lib/platform";

export function AgeScreen({ onEligible }: { onEligible: (token: string) => void }) {
  const [band, setBand] = useState("");
  const [blocked, setBlocked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function check(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const result = await platformRequest<{ eligible: boolean; age_check_token: string }>("/api/accounts/age-check", { age_band: band });
      setBand("");
      if (result.eligible) onEligible(result.age_check_token);
      else setBlocked(true);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выполнить проверку."); }
    finally { setBusy(false); }
  }
  if (blocked) return <p className="notice" role="status">Для несовершеннолетних нужен отдельный процесс доступа через учреждение и законного представителя. Он пока не запущен; самостоятельная регистрация недоступна.</p>;
  return <form className="auth-form" onSubmit={(event) => void check(event)} data-private="true">
    <p>Сначала укажите возрастную группу. Дата рождения не требуется.</p>
    <label>Возрастная группа<select required value={band} onChange={(event) => setBand(event.target.value)}>
      <option value="" disabled>Выберите группу</option><option value="under_13">До 13 лет</option><option value="13_to_17">13–17 лет</option><option value="18_or_over">18 лет и старше</option>
    </select></label>
    <button className="button primary" type="submit" disabled={busy || !band}>{busy ? "Проверяем…" : "Продолжить"}</button>
    {error && <p className="notice error-notice" role="alert">{error}</p>}
  </form>;
}
