"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { AuthStudy } from "./auth-study";
import { FormaMark } from "./forma-mark";
import { platformRequest } from "../lib/platform";

type Consent = {status: string; request_code: string; notice: string; notice_url: string; privacy_contact: string};
export function GuardianConsent() {
  const [data,setData]=useState<Consent|null>(null); const [token,setToken]=useState("");
  const [adult,setAdult]=useState(false); const [consent,setConsent]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
  useEffect(() => { let live=true; const value=new URLSearchParams(window.location.search).get("token")??""; setToken(value);
    if (!value) {setError("В ссылке нет кода подтверждения. Попросите отправить письмо ещё раз.");return;}
    void platformRequest<Consent>("/api/accounts/guardian-consent/inspect",{token:value}).then(result=>{if(live)setData(result);}).catch(cause=>{if(live)setError(cause instanceof Error?cause.message:"Не удалось открыть запрос.");}); return()=>{live=false;};
  },[]);
  async function decide(decision: "approve"|"decline") {
    if (!data || busy || (decision==="approve" && (!adult || !consent))) return;
    setBusy(true);setError("");
    try {const result=await platformRequest<{status:string}>("/api/accounts/guardian-consent/decision",{token,decision,adult_guardian:adult,consent});setData({...data,status:result.status});}
    catch(cause){setError(cause instanceof Error?cause.message:"Решение не сохранено. Попробуйте снова.");} finally{setBusy(false);}
  }
  return <main className="auth-page"><AuthStudy/><section className="auth-card"><Link href="/" className="forma-brand auth-brand"><FormaMark/>forma<span className="brand-period">.</span></Link><div className="eyebrow">РОДИТЕЛЮ / ЗАКОННОМУ ПРЕДСТАВИТЕЛЮ</div><h1>Согласие на регистрацию</h1>
    {!data && !error && <p role="status">Открываем запрос…</p>}
    {data && <div className="auth-form"><div className="age-request-code"><span>Сверьте код с ребёнком</span><strong>{data.request_code}</strong></div>
      {data.status === "pending" ? <><p>Ребёнок 13–17 лет хочет создать учётную запись Forma. Открытие этой страницы само по себе не даёт согласия.</p><p>{data.notice}</p><a href={data.notice_url} target="_blank" rel="noreferrer">Уведомление об обработке персональных данных ↗</a>
        <label className="age-confirmation"><input type="checkbox" checked={adult} disabled={busy} onChange={e=>setAdult(e.target.checked)}/><span>Мне исполнилось 18 лет, я родитель или законный представитель этого ребёнка.</span></label>
        <label className="age-confirmation"><input type="checkbox" checked={consent} disabled={busy} onChange={e=>setConsent(e.target.checked)}/><span>Я прочитал(а) уведомление и даю согласие на указанную обработку данных и регистрацию ребёнка.</span></label>
        <button className="button primary" disabled={busy||!adult||!consent} onClick={()=>void decide("approve")}>Разрешить регистрацию</button><button className="quiet-button" disabled={busy} onClick={()=>void decide("decline")}>Не разрешать</button>
      </> : <><p role="status">{data.status === "declined" ? "Согласие не предоставлено или отозвано. Регистрация и доступ ребёнка заблокированы." : data.status === "consumed" ? "Ребёнок создал учётную запись с вашим согласием." : "Согласие сохранено. Ребёнок может вернуться к регистрации и продолжить."}</p>{["approved","consumed"].includes(data.status) && <button className="quiet-button" disabled={busy} onClick={()=>{if(window.confirm("Отозвать согласие и закрыть доступ к учётной записи ребёнка?"))void decide("decline");}}>Отозвать согласие</button>}</>}
      <p>По вопросам обработки данных и отзыва согласия: <a href={`mailto:${data.privacy_contact}`}>{data.privacy_contact}</a>.</p>
    </div>}{error && <p className="notice error-notice" role="alert">{error}</p>}
  </section></main>;
}
