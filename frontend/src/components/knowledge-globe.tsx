"use client";

import { useEffect, useRef } from "react";
import { globeLand } from "../lib/globe-land";

type Vector = readonly [number, number, number];
const radians = Math.PI / 180;
function sphere(longitude: number, latitude: number): Vector {
  const lat = latitude * radians, lon = longitude * radians;
  return [Math.cos(lat) * Math.sin(lon), -Math.sin(lat), Math.cos(lat) * Math.cos(lon)];
}
const land = globeLand.map(([longitude, latitude]) => sphere(longitude, latitude));
const cities = [[127, 37], [-74, 41], [0, 51], [139, 36], [104, 1], [151, -34], [2, 49], [77, 29], [-122, 38]].map(([lon, lat]) => sphere(lon, lat));
const links = [[0, 1], [0, 2], [0, 3], [0, 4], [2, 7], [4, 5], [1, 8], [2, 6], [3, 8]];
const meridians = Array.from({ length: 12 }, (_, i) => Array.from({ length: 61 }, (_, j) => sphere(i * 30, -90 + j * 3)));
const parallels = [-60, -30, 0, 30, 60].map(lat => Array.from({ length: 121 }, (_, j) => sphere(-180 + j * 3, lat)));

/** Decorative local canvas: no WebGL, tracking, live data, external scripts, or network requests. */
export function KnowledgeGlobe({ paused = false, login = false }: { paused?: boolean; login?: boolean }) {
  const element = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = element.current;
    const context = canvas?.getContext("2d", { alpha: false });
    if (!canvas || !context) return;
    let width = 0, height = 0, frame = 0, last = 0, elapsed = 0, visible = true, destroyed = false;
    let mouse = 0;
    function draw() {
      if (!context || !width || !height) return;
      context.fillStyle = "#040408"; context.fillRect(0, 0, width, height);
      const radius = login ? Math.min(width * (width < 700 ? .94 : .53), height * .9) : Math.min(width * .49, height * .92);
      const cx = width * (login && width >= 700 ? .32 : .5), cy = height * (login ? .8 : .88);
      const yaw = -.55 + elapsed * .000032 + mouse * .045;
      const tilt = -.14;
      const project = ([x, y, z]: Vector) => {
        const xx = x * Math.cos(yaw) + z * Math.sin(yaw), zz = -x * Math.sin(yaw) + z * Math.cos(yaw);
        const yy = y * Math.cos(tilt) - zz * Math.sin(tilt), depth = y * Math.sin(tilt) + zz * Math.cos(tilt);
        return { x: cx + xx * radius, y: cy + yy * radius, depth };
      };
      // Deterministic stars remain stable across resize and motion changes.
      for (let i = 1; i < 100; i++) {
        const x = ((i * 127.13) % 997) / 997 * width, y = ((i * 89.79) % 991) / 991 * height;
        const twinkle = .25 + .4 * ((Math.sin(i + elapsed * .00045) + 1) / 2);
        context.fillStyle = `rgba(222,215,255,${twinkle})`; context.fillRect(x, y, i % 13 === 0 ? 2 : 1, i % 13 === 0 ? 2 : 1);
      }
      const atmosphere = context.createRadialGradient(cx, cy, radius * .88, cx, cy, radius * 1.075);
      atmosphere.addColorStop(0, "#08061000"); atmosphere.addColorStop(.52, "#7752e525"); atmosphere.addColorStop(.66, "#ac8aff85"); atmosphere.addColorStop(.73, "#7850e735"); atmosphere.addColorStop(1, "#30114d00");
      context.fillStyle = atmosphere; context.beginPath(); context.arc(cx, cy, radius * 1.075, 0, Math.PI * 2); context.fill();
      const interior = context.createRadialGradient(cx - radius * .2, cy - radius * .8, 0, cx, cy, radius);
      interior.addColorStop(0, "#1f1237"); interior.addColorStop(.55, "#090713"); interior.addColorStop(1, "#06050b");
      context.fillStyle = interior; context.beginPath(); context.arc(cx, cy, radius, 0, Math.PI * 2); context.fill();
      context.lineWidth = .7; context.strokeStyle = "#a183eb20";
      for (const line of [...meridians, ...parallels]) {
        context.beginPath(); let running = false;
        for (const point of line) { const p = project(point); if (p.depth < 0) { running = false; continue; } if (!running) context.moveTo(p.x, p.y); else context.lineTo(p.x, p.y); running = true; }
        context.stroke();
      }
      // Land dots use a real public-domain coastline, sampled once at build time.
      for (const point of land) {
        const p = project(point); if (p.depth < .01) continue;
        context.fillStyle = `rgba(161,132,245,${.15 + p.depth * .55})`;
        const dot = Math.max(.65, radius * .00175) * (.5 + p.depth * .5);
        context.beginPath(); context.arc(p.x, p.y, dot, 0, Math.PI * 2); context.fill();
      }
      for (let k = 0; k < links.length; k++) {
        const [from, to] = links[k], a = cities[from], b = cities[to];
        context.beginPath(); let started = false;
        for (let n = 0; n <= 40; n++) {
          const t = n / 40, vector = a.map((v, i) => v * (1 - t) + b[i] * t), length = Math.hypot(...vector);
          const lift = 1 + Math.sin(t * Math.PI) * .08;
          const p = project(vector.map(v => v / length * lift) as unknown as Vector);
          if (p.depth < 0) { started = false; continue; }
          if (!started) context.moveTo(p.x, p.y); else context.lineTo(p.x, p.y); started = true;
        }
        context.strokeStyle = "#b69afc50"; context.lineWidth = .85; context.stroke();
      }
      for (const city of cities) {
        const p = project(city); if (p.depth < .05) continue;
        const pulse = 5 + (Math.sin(elapsed * .0016 + city[0] * 4) + 1) * 3;
        const light = context.createRadialGradient(p.x, p.y, 0, p.x, p.y, pulse * 2);
        light.addColorStop(0, "#e0d3ff"); light.addColorStop(.15, "#b99affd0"); light.addColorStop(.45, "#9866ff40"); light.addColorStop(1, "#7851dd00");
        context.fillStyle = light; context.beginPath(); context.arc(p.x, p.y, pulse * 2, 0, Math.PI * 2); context.fill();
        context.strokeStyle = "#e1d6ff75"; context.lineWidth = .7; context.beginPath(); context.moveTo(p.x - 7, p.y); context.lineTo(p.x + 7, p.y); context.moveTo(p.x, p.y - 7); context.lineTo(p.x, p.y + 7); context.stroke();
      }
    }
    function animate(time: number) {
      frame = 0;
      if (destroyed || !visible || document.hidden || paused) return;
      if (time - last >= 33) { elapsed += last ? Math.min(time - last, 60) : 0; last = time; draw(); }
      frame = requestAnimationFrame(animate);
    }
    function resume() { cancelAnimationFrame(frame); frame = 0; last = 0; draw(); if (visible && !document.hidden && !paused) frame = requestAnimationFrame(animate); }
    function resize() {
      const box = canvas!.getBoundingClientRect(); width = box.width; height = box.height;
      const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas!.width = Math.round(width * ratio); canvas!.height = Math.round(height * ratio);
      context!.setTransform(ratio, 0, 0, ratio, 0, 0); resume();
    }
    const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(canvas);
    const observer = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; resume(); }); observer.observe(canvas);
    const pointer = (event: PointerEvent) => { mouse = event.clientX / Math.max(width, 1) - .5; };
    window.addEventListener("pointermove", pointer, { passive: true });
    document.addEventListener("visibilitychange", resume); resize();
    return () => { destroyed = true; cancelAnimationFrame(frame); resizeObserver.disconnect(); observer.disconnect(); window.removeEventListener("pointermove", pointer); document.removeEventListener("visibilitychange", resume); };
  }, [paused, login]);
  return <div className={`ms-globe${login ? " ms-globe-login" : ""}`} aria-hidden="true"><div className="ms-globe-fallback"/><canvas ref={element}/></div>;
}
