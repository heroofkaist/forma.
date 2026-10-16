"use client";
import { useEffect, useState } from "react";
import { Pause, Play } from "lucide-react";
export function useSceneMotion() {
  const [paused, setPaused] = useState(false);
  useEffect(() => { const preference = window.matchMedia("(prefers-reduced-motion: reduce)"); setPaused(preference.matches); const change = () => setPaused(preference.matches); preference.addEventListener("change", change); return () => preference.removeEventListener("change", change); }, []);
  return { paused, toggle: () => setPaused(value => !value) };
}
export function MotionControl({ paused, onToggle }: { paused: boolean; onToggle: () => void }) {
  return <button className="ms-motion-control" type="button" onClick={onToggle} aria-pressed={paused} aria-label={paused ? "Включить анимацию" : "Остановить анимацию"}>{paused ? <Play size={14} aria-hidden="true"/> : <Pause size={14} aria-hidden="true"/>}<span>{paused ? "Анимация выключена" : "Остановить анимацию"}</span></button>;
}
