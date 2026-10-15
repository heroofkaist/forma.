"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";

const perspectives = ["Целое", "Детали", "Связи"];

/** Deterministic optical artwork. No inference, external assets or continuous JS loop. */
export function FormStudy({ compact = false }: { compact?: boolean }) {
  const root = useRef<HTMLDivElement>(null);
  const [perspective, setPerspective] = useState(0);
  const [paused, setPaused] = useState(compact);
  const [visible, setVisible] = useState(false);
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const motion = () => setReduced(media.matches);
    let intersecting = false;
    const visibility = () => setVisible(!document.hidden && intersecting);
    const observer = new IntersectionObserver(([entry]) => { intersecting = entry.isIntersecting; visibility(); });
    if (root.current) observer.observe(root.current);
    motion();
    media.addEventListener("change", motion);
    document.addEventListener("visibilitychange", visibility);
    return () => { observer.disconnect(); media.removeEventListener("change", motion); document.removeEventListener("visibilitychange", visibility); };
  }, []);

  const paths = useMemo(() => Array.from({ length: 46 }, (_, layer) => {
    const radius = 44 + layer * 3.55;
    return Array.from({ length: 161 }, (_, point) => {
      const t = point / 160 * Math.PI * 2;
      const twist = layer * .027 + perspective * .4;
      const r = radius * (1 + (.19 + perspective * .025) * Math.cos(3 * t + twist));
      const x = 260 + r * Math.cos(t) * .96;
      const y = 255 + r * Math.sin(t) * .96;
      return `${point ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ") + "Z";
  }), [perspective]);

  return <div ref={root} className={`optical-study ${compact ? "optical-compact" : ""}`}>
    <div className="optical-index"><span>ОБЪЕКТ № 01</span><span>ОПТИКА МЫСЛИ ↙</span></div>
    <div className="optical-stage">
      <span className="optical-cross optical-cross-a" aria-hidden="true">+</span>
      <span className="optical-cross optical-cross-b" aria-hidden="true">+</span>
      <svg viewBox="0 0 520 520" role="img" aria-label="Оптическая скульптура: множество контуров складываются в трёхлепестковую форму">
        <circle className="optical-orbit" cx="260" cy="260" r="239"/>
        <g className="optical-turn" style={{ animationPlayState: paused || reduced || !visible ? "paused" : "running" }}>
          {paths.map((d, i) => <path key={i} d={d} className={i > 31 ? "optical-outer" : "optical-inner"}/>)}
        </g>
        <circle className="optical-core" cx="260" cy="255" r="21"/>
        <path className="optical-needle" d="M250 265 270 245M250 245h20v20"/>
      </svg>
      <span className="optical-stamp">f<span>в процессе<br/>понимания</span></span>
      <span className="optical-caption">Один предмет.<br/>Множество прочтений.</span>
    </div>
    {!compact && <>
      <div className="optical-controls"><div role="group" aria-label="Перспектива графической композиции">{perspectives.map((label, i) => <button key={label} aria-pressed={perspective === i} onClick={() => setPerspective(i)}><span>0{i + 1}</span>{label}</button>)}</div><button className="optical-pause" aria-label={paused ? "Включить движение" : "Остановить движение"} onClick={() => setPaused(v => !v)} disabled={reduced}>{paused || reduced ? <Play size={16}/> : <Pause size={16}/>}</button></div>
      <p className="optical-footnote">Интерактивная графика · не анализ ИИ</p>
    </>}
  </div>;
}
