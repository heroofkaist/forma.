import { FormStudy } from "./form-study";
export function AuthStudy() {
  return <aside className="auth-study"><div className="auth-study-top"><span>FORMA /</span><span>БЮРО МЫСЛИ</span></div><h2>Смотрим<br/>глубже<span className="ink-dot">.</span></h2><FormStudy compact/><div className="auth-study-bottom"><span>У КАЖДОЙ РАБОТЫ<br/>ЕСТЬ СВОЯ ЛОГИКА.</span><p>ИИ предлагает прочтение.<br/>Человек принимает решение.</p></div></aside>;
}
