"use client";
import { useState } from "react";
import Link from "next/link";
import { platformRequest } from "../../lib/platform";
import { useAuth } from "../../components/auth-provider";
export default function Invitation() {
  const { user } = useAuth(); const [confirmed, setConfirmed] = useState(false); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  async function accept() { setBusy(true); try { const token = new URLSearchParams(window.location.search).get("token") ?? ""; const result = await platformRequest("/api/institutions/invitations/accept", {token, confirm_role_transition:confirmed}); setMessage("Приглашение принято. Войдите снова, чтобы продолжить как преподаватель."); window.location.assign('/teacher'); } catch (error) { setMessage(error instanceof Error ? error.message : "Ошибка приглашения."); } finally {setBusy(false);} }
  return <main className="auth-page"><section className="auth-card"><h1>Приглашение преподавателя</h1><p>Приглашение выдаёт права только в указанном учреждении. Активные записи студента требуют предварительной административной проверки.</p>{!user ? <Link href="/login?next=/teacher-invitation">Войдите подтверждённой учётной записью, затем откройте ссылку из письма снова.</Link> : <><label><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />Подтверждаю переход к роли преподавателя</label><button className="button primary" disabled={!confirmed || busy} onClick={() => void accept()}>Принять приглашение</button></>}{message && <p role="status">{message}</p>}</section></main>;
}
