import React from "react";
import { Easing, Img, interpolate, staticFile, useCurrentFrame } from "remotion";

export const FPS = 30;
export const W = 1080;
export const H = 1920;

export const C = {
  space: "#0b0b0c",
  panel: "#18181a",
  line: "#2e2e31",
  text: "#f5f4ef",
  muted: "#a3a29b",
  faint: "#6f6e69",
  amber: "#f5b83d",
  red: "#ff6b5e",
  term: "#1e232d",   // 取自真实终端录屏的背景色
  ui: "#fdfdfd",     // 取自真实系统设置截图的背景色，全屏出血时边缘没有接缝
  green: "#34c759",
};
export const FONT = '"PingFang SC", "Helvetica Neue", "Hiragino Sans GB", sans-serif';
export const MONO = '"SF Mono", Menlo, monospace';

export const E_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const E_IN = Easing.bezier(0.7, 0, 0.84, 0);
export const E_IO = Easing.bezier(0.65, 0, 0.35, 1);

/** 当前镜头内的时间（秒） */
export const useT = () => useCurrentFrame() / FPS;

export const lerp = (t: number, input: number[], output: number[], easing: (n: number) => number = E_OUT) =>
  interpolate(t, input, output, { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing });

export type CamKey = { t: number; x: number; y: number; z: number };

/**
 * 虚拟摄影机：把一块“底板”（真实截图或录屏，按它自己的像素坐标）拍进竖屏画面。
 * 每个关键帧说明：此刻镜头对准底板上的哪个点（x, y），放大多少（z）。
 */
export const Cam: React.FC<{
  w: number; h: number; keys: CamKey[]; ax?: number; ay?: number; easing?: (n: number) => number;
  children: React.ReactNode; style?: React.CSSProperties;
}> = ({ w, h, keys, ax = W / 2, ay = H * 0.44, easing = E_IO, children, style }) => {
  const t = useT();
  const ts = keys.map((k) => k.t);
  const pick = (f: (k: CamKey) => number) => (keys.length === 1 ? f(keys[0]) : lerp(t, ts, keys.map(f), easing));
  const x = pick((k) => k.x), y = pick((k) => k.y), z = pick((k) => k.z);
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: w, height: h, transformOrigin: "0 0",
      transform: `translate(${ax - x * z}px, ${ay - y * z}px) scale(${z})`, ...style }}>
      {children}
    </div>
  );
};

export const Plate: React.FC<{ src: string; w: number; h: number; style?: React.CSSProperties }> = ({ src, w, h, style }) => (
  <Img src={staticFile(src)} style={{ position: "absolute", left: 0, top: 0, width: w, height: h, display: "block", ...style }} />
);

/** macOS 的箭头光标（合成的） */
export const Cursor: React.FC<{ x: number; y: number; scale?: number; pressed?: boolean }> = ({ x, y, scale = 1, pressed }) => (
  <svg width={44 * scale} height={64 * scale} viewBox="0 0 22 32" style={{ position: "absolute", left: x, top: y, overflow: "visible",
    filter: "drop-shadow(0 3px 5px rgba(0,0,0,0.45))", transform: pressed ? "scale(0.9)" : undefined, transformOrigin: "0 0" }}>
    <path d="M1 1 L1 25 L7.2 19.4 L11.4 29.5 L15.2 27.9 L11.1 18 L19.5 18 Z" fill="#111" stroke="#fff" strokeWidth="1.6" strokeLinejoin="round" />
  </svg>
);

/** 一个 macOS 样式的开关，用来盖在真实界面的开关上演示“被拨开” */
export const Toggle: React.FC<{ x: number; y: number; w: number; h: number; on: number }> = ({ x, y, w, h, on }) => (
  <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: h / 2,
    background: `color-mix(in srgb, ${C.green} ${on * 100}%, #d4d4d4)`, boxShadow: "inset 0 0 0 1px rgba(0,0,0,0.06)" }}>
    <div style={{ position: "absolute", top: 2, left: 2 + on * (w - h), width: h - 4, height: h - 4, borderRadius: "50%",
      background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.3)" }} />
  </div>
);

/** 屏幕关键词：大、少、有动势；没有底板 */
export const Keyword: React.FC<{
  text: string; at: number; out?: number; x?: number; y: number; size?: number; color?: string; align?: "left" | "center";
  shadow?: boolean; weight?: number;
}> = ({ text, at, out, x = W / 2, y, size = 96, color = C.text, align = "center", shadow = true, weight = 800 }) => {
  const t = useT();
  if (t < at - 0.05 || (out !== undefined && t > out + 0.2)) return null;
  const o = out === undefined ? lerp(t, [at, at + 0.14], [0, 1]) : lerp(t, [at, at + 0.14, out, out + 0.16], [0, 1, 1, 0], Easing.linear);
  return (
    <div style={{ position: "absolute", left: align === "center" ? 0 : x, width: align === "center" ? W : undefined, top: y,
      textAlign: align, fontSize: size, fontWeight: weight, color, letterSpacing: 2, lineHeight: 1.15, opacity: o,
      translate: `0px ${lerp(t, [at, at + 0.45], [36, 0])}px`, scale: `${lerp(t, [at, at + 0.4], [0.92, 1])}`,
      textShadow: shadow ? "0 6px 30px rgba(0,0,0,0.55)" : undefined, whiteSpace: "nowrap" }}>
      {text}
    </div>
  );
};

/** 浅色画面上要放白色关键词时，垫在下面的一条暗色渐变 */
export const Scrim: React.FC<{ top?: number; strength?: number }> = ({ top = 940, strength = 0.86 }) => (
  <div style={{ position: "absolute", left: 0, top, width: W, height: H - top,
    background: `linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,${strength}) 26%, rgba(0,0,0,${strength}) 100%)` }} />
);

export const Badge: React.FC<{ text: string; x?: number; y?: number; dark?: boolean }> = ({ text, x = 48, y = 150, dark }) => (
  <div style={{ position: "absolute", left: x, top: y, fontSize: 26, padding: "8px 16px", borderRadius: 10, letterSpacing: 1,
    color: dark ? "#333" : C.muted, background: dark ? "rgba(255,255,255,0.82)" : "rgba(255,255,255,0.08)",
    border: `1px solid ${dark ? "rgba(0,0,0,0.12)" : "rgba(255,255,255,0.14)"}` }}>{text}</div>
);

/** 高亮框：盖在底板上的某个区域（底板坐标） */
export const Box: React.FC<{ x: number; y: number; w: number; h: number; at: number; pad?: number; dim?: boolean; color?: string }> = ({
  x, y, w, h, at, pad = 10, dim = true, color = C.amber,
}) => {
  const t = useT();
  const p = lerp(t, [at, at + 0.28], [0, 1]);
  if (t < at) return null;
  return (
    <div style={{ position: "absolute", left: x - pad, top: y - pad, width: (w + pad * 2) * p, height: h + pad * 2, borderRadius: 10,
      border: `4px solid ${color}`, background: "rgba(245,184,61,0.18)", boxSizing: "border-box",
      boxShadow: dim ? `0 0 0 3000px rgba(0,0,0,${0.3 * p})` : undefined }} />
  );
};
