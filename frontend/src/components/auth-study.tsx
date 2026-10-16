import Link from "next/link";
import { Check } from "lucide-react";
import { FormaMark } from "./forma-mark";
import { ProductTour } from "./product-tour";
export function AuthStudy() {
  return <aside className="auth-study"><Link href="/" className="forma-brand" aria-label="Forma · главная"><FormaMark/>forma<span className="brand-period">.</span></Link><div className="auth-study-intro"><span className="eyebrow">ВАШЕ УЧЕБНОЕ ПРОСТРАНСТВО</span><h2>От работы<br/>к пониманию.</h2><p>Меньше переключений между файлами.<br/>Больше внимания к обратной связи.</p></div><ProductTour compact/><div className="auth-study-bottom"><Check size={18} aria-hidden="true"/><p>ИИ предлагает баллы.<br/><strong>Преподаватель принимает решение.</strong></p></div></aside>;
}
