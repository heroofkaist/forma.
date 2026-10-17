"use client";

import { useEffect, useRef, useState } from "react";
import { Check, FileText, ListChecks, MessageSquare, ArrowRight } from "lucide-react";

const steps = [
  { label: "Работа студента", short: "Работа", icon: FileText, title: "Решение задачи", detail: "Студент объяснил метод и показал вычисления.", score: "F = ma" },
  { label: "Проверка по критериям", short: "Критерии", icon: ListChecks, title: "Ответ и единицы", detail: "Решение верное. В ответе не хватает единиц измерения.", score: "8 / 10" },
  { label: "Комментарий преподавателя", short: "Результат", icon: MessageSquare, title: "Отзыв", detail: "Метод выбран верно. Добавьте единицы в ответ.", score: "Проверено" },
];

/** Articulated SVG characters and a live HTML example. No video or inference request. */
export function LearningScene({ paused = false, compact = false }: { paused?: boolean; compact?: boolean }) {
  const [step, setStep] = useState(0);
  const surface = useRef<HTMLDivElement>(null);
  const target = useRef({ x: 0, y: 0 });
  const hovering = useRef(false);
  const focused = useRef(false);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = surface.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(node); return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (paused || !visible) return;
    const timer = window.setInterval(() => { if (!document.hidden && !hovering.current && !focused.current) setStep(value => (value + 1) % steps.length); }, 6500);
    return () => window.clearInterval(timer);
  }, [paused, visible]);
  useEffect(() => {
    const node = surface.current;
    if (!node) return;
    let frame = 0, x = 0, y = 0, vx = 0, vy = 0;
    function reset() { target.current = { x: 0, y: 0 }; }
    function move(event: PointerEvent) {
      if (paused || event.pointerType === "touch") return;
      const box = node!.getBoundingClientRect();
      target.current = { x: Math.max(-1, Math.min(1, (event.clientX - box.left) / box.width * 2 - 1)), y: Math.max(-1, Math.min(1, (event.clientY - box.top) / box.height * 2 - 1)) };
    }
    function draw() {
      frame = 0;
      if (paused || !visible || document.hidden) return;
      vx = (vx + (target.current.x - x) * .045) * .77;
      vy = (vy + (target.current.y - y) * .045) * .77;
      x += vx; y += vy;
      node!.style.setProperty("--scene-x", `${(x * 13).toFixed(2)}px`);
      node!.style.setProperty("--scene-y", `${(y * 8).toFixed(2)}px`);
      node!.style.setProperty("--scene-turn", `${(x * 4).toFixed(2)}deg`);
      frame = requestAnimationFrame(draw);
    }
    function resume() { cancelAnimationFrame(frame); frame = 0; if (!paused && visible && !document.hidden) frame = requestAnimationFrame(draw); }
    node.addEventListener("pointermove", move, { passive: true }); node.addEventListener("pointerleave", reset);
    document.addEventListener("visibilitychange", resume); resume();
    if (paused) { node.style.setProperty("--scene-x", "0px"); node.style.setProperty("--scene-y", "0px"); node.style.setProperty("--scene-turn", "0deg"); }
    return () => { cancelAnimationFrame(frame); node.removeEventListener("pointermove", move); node.removeEventListener("pointerleave", reset); document.removeEventListener("visibilitychange", resume); };
  }, [paused, visible]);
  const current = steps[step];
  return <div ref={surface} className={`cf-learning-scene${compact ? " is-compact" : ""}`} data-step={step} data-paused={paused} data-visible={visible} onPointerEnter={() => { hovering.current = true; }} onPointerLeave={() => { hovering.current = false; }} onFocusCapture={() => { focused.current = true; }} onBlurCapture={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) focused.current = false; }}>
    <svg className="cf-scene-art" viewBox="0 0 1100 540" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="cf-shirt" x1="180" y1="275" x2="320" y2="430" gradientUnits="userSpaceOnUse"><stop stopColor="#9bc5ff"/><stop offset=".5" stopColor="#487bd9"/><stop offset="1" stopColor="#3456a5"/></linearGradient>
        <linearGradient id="cf-skin" x1="220" y1="170" x2="280" y2="270" gradientUnits="userSpaceOnUse"><stop stopColor="#ffdfc5"/><stop offset=".6" stopColor="#eab68e"/><stop offset="1" stopColor="#ce8f70"/></linearGradient>
        <linearGradient id="cf-coat" x1="830" y1="265" x2="925" y2="430" gradientUnits="userSpaceOnUse"><stop stopColor="#fffef5"/><stop offset=".5" stopColor="#e4e1d5"/><stop offset="1" stopColor="#b4c2ce"/></linearGradient>
        <linearGradient id="cf-teacher-skin" x1="855" y1="170" x2="920" y2="275" gradientUnits="userSpaceOnUse"><stop stopColor="#e4b18c"/><stop offset=".7" stopColor="#c98c68"/><stop offset="1" stopColor="#a86f52"/></linearGradient>
        <linearGradient id="cf-podium" x1="550" y1="390" x2="550" y2="505" gradientUnits="userSpaceOnUse"><stop stopColor="#fff"/><stop offset=".45" stopColor="#edf4ff"/><stop offset="1" stopColor="#c2d6f0"/></linearGradient>
        <linearGradient id="cf-orb" x1="140" y1="80" x2="195" y2="140" gradientUnits="userSpaceOnUse"><stop stopColor="#e8f8ff"/><stop offset=".5" stopColor="#b4d8fd"/><stop offset="1" stopColor="#83aae5"/></linearGradient>
        <radialGradient id="cf-sphere"><stop stopColor="#f8fcff"/><stop offset=".5" stopColor="#b9dcff"/><stop offset="1" stopColor="#709be1"/></radialGradient>
        <filter id="cf-soft-shadow" x="-30%" y="-30%" width="160%" height="180%"><feDropShadow dx="0" dy="12" stdDeviation="12" floodColor="#4470a9" floodOpacity=".12"/></filter>
      </defs>
      <ellipse cx="550" cy="485" rx="435" ry="28" fill="#527eb2" opacity=".07"/>
      <g className="cf-scene-platform"><path d="M142 407v29c0 43 183 78 408 78s408-35 408-78v-29H142Z" fill="url(#cf-podium)"/><ellipse cx="550" cy="407" rx="408" ry="78" fill="#f8fcff"/><ellipse cx="550" cy="407" rx="376" ry="62" stroke="#d9e9fa"/></g>
      <path className="cf-transfer-path" d="M310 296Q550 62 790 296" stroke="#a2c3ed" strokeWidth="1.5" strokeDasharray="5 9"/>
      <g className="cf-satellite cf-satellite-sphere"><circle cx="165" cy="126" r="32" fill="url(#cf-sphere)"/><ellipse cx="165" cy="126" rx="48" ry="13" stroke="#e9f5ff" strokeWidth="3" transform="rotate(-24 165 126)"/></g>
      <g className="cf-satellite cf-satellite-cube"><path d="m945 105 33-18 33 18-33 19-33-19Z" fill="#f5faff"/><path d="m945 105 33 19v39l-33-20v-38Z" fill="#bfd6f9"/><path d="m978 124 33-19v38l-33 20v-39Z" fill="#85a9e6"/></g>
      <g className="cf-satellite cf-satellite-note" transform="rotate(12 730 110)"><rect x="705" y="72" width="52" height="68" rx="8" fill="#fff" stroke="#d3e4f8"/><path d="M718 92h24m-24 11h18m-18 11h22" stroke="#b5cce9" strokeWidth="3" strokeLinecap="round"/></g>
      <g className="cf-person cf-student">
        <ellipse cx="253" cy="424" rx="88" ry="16" fill="#6d93c0" opacity=".13"/>
        <path d="M213 361c-12 21-14 40-4 54 8 12 25 12 37 6l32-18-10-33-55-9Z" fill="#29436f"/><path d="M268 368c12 9 24 19 28 32l-4 16-17 2c-9-16-24-20-43-27l36-23Z" fill="#365687"/>
        <path d="m220 407 18 2 3 13-24 9c-13 4-31 0-30-8 1-6 18-8 33-16Zm65 0 15 5 18 13c6 7-6 11-18 8l-25-8 10-18Z" fill="#f7fbff" stroke="#cdddf1"/>
        <path d="M220 271c-29 11-39 49-32 82 6 25 24 35 59 35 39 0 62-12 62-38 0-30-17-67-41-78l-48-1Z" fill="url(#cf-shirt)"/>
        <path d="M221 272c8 13 32 17 48 1l-5-24-39 1-4 22Z" fill="#dfaa84"/>
        <path d="M209 294c-19 13-27 41-18 59" stroke="#75a3ed" strokeWidth="22" strokeLinecap="round"/>
        <g className="cf-student-arm"><path d="M282 295c11 24 34 30 56 11" stroke="#5d8de0" strokeWidth="23" strokeLinecap="round"/><path d="m337 305 18-13" stroke="#e8b58f" strokeWidth="16" strokeLinecap="round"/><path d="m355 293 7-8m-7 8 10-3" stroke="#e8b58f" strokeWidth="6" strokeLinecap="round"/></g>
        <g className="cf-person-head cf-student-head"><path d="M206 212c0-35 16-53 44-53 29 0 45 24 43 52l-4 29c-3 23-20 35-40 33-23-2-37-16-40-38l-3-23Z" fill="url(#cf-skin)"/><ellipse cx="208" cy="225" rx="7" ry="12" fill="#e7b38c"/><path d="M207 211c-5-24 2-45 23-54 18-9 46-2 56 11 10 12 10 31 5 45l-12-14-1-19c-17 10-36 13-57 7l-3 23-11 1Z" fill="#423e48"/><path d="M220 171c13-10 30-12 46-4" stroke="#625766" strokeWidth="6" strokeLinecap="round"/><g className="cf-person-eyes"><ellipse cx="237" cy="223" rx="3" ry="4" fill="#424a5b"/><ellipse cx="271" cy="222" rx="3" ry="4" fill="#424a5b"/></g><path d="m254 225-3 11h7" stroke="#c68c6d" strokeWidth="2" strokeLinecap="round"/><path d="M244 246q11 7 20-1" stroke="#a96e59" strokeWidth="2.5" strokeLinecap="round"/><path d="M230 212q6-3 12-1m23-1q6-3 11 0" stroke="#6d5050" strokeWidth="2" strokeLinecap="round"/></g>
      </g>
      <g className="cf-person cf-teacher">
        <ellipse cx="859" cy="424" rx="85" ry="16" fill="#6d93c0" opacity=".13"/>
        <path d="M822 354c-11 31-7 53 10 60l33-9 2-41-45-10Z" fill="#57718e"/><path d="M872 357c10 14 20 36 18 54l-20 9-16-24-4-31 22-8Z" fill="#6f879d"/>
        <path d="m834 406 17 1-2 15-31 8c-13 2-25-3-18-10l34-14Zm41 4 18 2 16 12c7 6-2 11-15 9l-28-8 9-15Z" fill="#fffdfa" stroke="#cdddf1"/>
        <path d="M829 266c-28 16-41 52-38 84 3 26 29 39 65 39 37 0 67-12 62-43-4-30-20-65-46-80h-43Z" fill="url(#cf-coat)"/>
        <path d="M834 266c10 11 25 12 38 0l-3-22-31 1-4 21Z" fill="#b97f5d"/>
        <path d="M834 278c2 29 13 48 21 58 9-12 18-34 20-58" fill="#92b2ce"/><path d="m827 281 19 35-10 9-13-30m57-14-18 34 10 11 13-32" stroke="#fffef8" strokeWidth="4" strokeLinejoin="round"/>
        <g className="cf-teacher-arm"><path d="M809 296c-16 23-34 25-53 8" stroke="#e9e8df" strokeWidth="25" strokeLinecap="round"/><path d="m756 304-16-16" stroke="#c58a66" strokeWidth="15" strokeLinecap="round"/><path d="m741 290-8-10m8 10-11-4" stroke="#c58a66" strokeWidth="5.5" strokeLinecap="round"/></g>
        <path d="M888 292c13 15 18 32 16 52" stroke="#c9d2d7" strokeWidth="23" strokeLinecap="round"/><path d="m903 342-6 15" stroke="#c58a66" strokeWidth="14" strokeLinecap="round"/>
        <g className="cf-person-head cf-teacher-head"><path d="M813 215c-5-38 7-66 39-67 36-2 53 29 48 72l-7 52h-83l3-57Z" fill="#5d4441"/><path d="M823 211c0-29 12-44 32-44 23 0 37 17 37 44v22c0 24-14 39-33 39-21 0-35-15-36-37v-24Z" fill="url(#cf-teacher-skin)"/><path d="M818 213c4-31 10-47 35-49 16 0 30 7 38 23-20 0-33-6-43-17-2 18-12 31-30 43Z" fill="#5d4441"/><path d="M823 176c8-14 25-20 40-13" stroke="#7f5951" strokeWidth="5" strokeLinecap="round"/><g className="cf-person-eyes"><ellipse cx="842" cy="221" rx="3" ry="4" fill="#3d3943"/><ellipse cx="872" cy="220" rx="3" ry="4" fill="#3d3943"/></g><path d="m857 223-3 12h6" stroke="#9e674b" strokeWidth="2" strokeLinecap="round"/><path d="M846 245q10 6 20-1" stroke="#895140" strokeWidth="2.5" strokeLinecap="round"/><g stroke="#5d6676" strokeWidth="2.2"><rect x="829" y="210" width="24" height="18" rx="7"/><rect x="862" y="209" width="23" height="18" rx="7"/><path d="m853 217 9-1"/></g></g>
      </g>
      <g className="cf-flying-sheet" filter="url(#cf-soft-shadow)"><rect x="324" y="224" width="70" height="89" rx="10" fill="white" stroke="#ccdef6"/><path d="M340 247h37m-37 12h25m-25 12h33" stroke="#a4bedf" strokeWidth="4" strokeLinecap="round"/><path d="m345 289 8 7 15-17" stroke="#6c9de0" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/></g>
    </svg>
    <div className="cf-example-panel" aria-label="Пример проверки"><header><span className="cf-example-dot"/>Пример работы<span className="cf-example-private">Только преподавателю</span></header><div className="cf-example-content"><span className="cf-example-kicker">{current.label}</span><div className="cf-example-title"><strong>{current.title}</strong><span>{current.score}</span></div><p>{current.detail}</p><span className="cf-example-source"><Check size={13} aria-hidden="true"/>{step === 2 ? "Результат готов к публикации" : "Исходный документ сохранён"}</span></div><div className="cf-scene-steps" role="group" aria-label="Посмотреть этап проверки">{steps.map((item, index) => <button type="button" key={item.short} aria-pressed={step === index} onClick={() => setStep(index)}><item.icon size={14} aria-hidden="true"/>{item.short}{step === index && <ArrowRight size={12} aria-hidden="true"/>}</button>)}</div></div>
    <p className="cf-scene-hint">{compact ? "Работы и оценки в одном месте" : "Выберите этап и посмотрите, как проходит проверка"}</p>
  </div>;
}
