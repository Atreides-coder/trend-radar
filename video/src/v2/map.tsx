import React from "react";
import { Img, staticFile } from "remotion";
import { C, lerp, useT, W, H } from "./kit";

/** 触达地图：五个真实的应用图标 + 一个备份盘。全片所有抽象概念都落在这张图上。 */
export const NODES = {
  finder: { x: 200, y: 920, icon: "assets/icon_finder.png", label: "文件" },
  safari: { x: 420, y: 560, icon: "assets/icon_safari.png", label: "浏览器" },
  mail: { x: 800, y: 620, icon: "assets/icon_mail.png", label: "邮件" },
  backup: { x: 880, y: 920, icon: "assets/icon_timemachine.png", label: "备份盘" },
  messages: { x: 790, y: 1250, icon: "assets/icon_messages.png", label: "信息" },
  terminal: { x: 400, y: 1290, icon: "assets/icon_terminal.png", label: "终端" },
} as const;
export type NodeId = keyof typeof NODES;
export type Pt = { x: number; y: number };

export const Node: React.FC<{
  id: NodeId; opacity?: number; size?: number; at?: number; ring?: string; ringAt?: number; label?: boolean;
}> = ({ id, opacity = 1, size = 184, at = 0, ring, ringAt = 0, label = true }) => {
  const t = useT();
  const n = NODES[id];
  const appear = lerp(t, [at, at + 0.35], [0, 1]);
  const pulse = ring ? (t - ringAt) % 0.9 : 0;
  return (
    <div style={{ position: "absolute", left: n.x - size / 2, top: n.y - size / 2, width: size, opacity: opacity * appear,
      scale: `${0.7 + 0.3 * appear}` }}>
      {ring && t >= ringAt && (
        <div style={{ position: "absolute", left: -20, top: -20, width: size + 40, height: size + 40, borderRadius: "50%",
          border: `5px solid ${ring}`, opacity: 1 - pulse / 0.9, scale: `${1 + pulse * 0.45}` }} />
      )}
      <Img src={staticFile(n.icon)} style={{ width: size, height: size, display: "block", filter: "drop-shadow(0 14px 26px rgba(0,0,0,0.6))" }} />
      {label && <div style={{ textAlign: "center", fontSize: 34, color: C.muted, marginTop: 6 }}>{n.label}</div>}
    </div>
  );
};

const lengthOf = (pts: Pt[]) => pts.slice(1).map((p, i) => Math.hypot(p.x - pts[i].x, p.y - pts[i].y));

/** 折线上按进度取点 */
export const pointAt = (pts: Pt[], progress: number): Pt => {
  const segs = lengthOf(pts);
  const total = segs.reduce((a, b) => a + b, 0);
  let d = Math.max(0, Math.min(1, progress)) * total;
  for (let i = 0; i < segs.length; i++) {
    if (d <= segs[i] || i === segs.length - 1) {
      const f = segs[i] === 0 ? 0 : Math.min(1, d / segs[i]);
      return { x: pts[i].x + (pts[i + 1].x - pts[i].x) * f, y: pts[i].y + (pts[i + 1].y - pts[i].y) * f };
    }
    d -= segs[i];
  }
  return pts[pts.length - 1];
};

/** 一条按进度画出来的路径，带一个发光的“线头” */
export const Path: React.FC<{
  pts: Pt[]; progress: number; color?: string; width?: number; head?: boolean; dashed?: boolean; opacity?: number;
}> = ({ pts, progress, color = C.amber, width = 10, head = true, dashed, opacity = 1 }) => {
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");
  const tip = pointAt(pts, progress);
  return (
    <svg width={W} height={H} style={{ position: "absolute", left: 0, top: 0, opacity }}>
      <path d={d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round"
        pathLength={1} strokeDasharray={dashed ? "0.015 0.02" : "1"} strokeDashoffset={dashed ? 0 : 1 - Math.max(0, Math.min(1, progress))}
        style={dashed ? { opacity: 0.55 } : undefined} />
      {head && progress > 0 && (
        <>
          <circle cx={tip.x} cy={tip.y} r={width * 2.6} fill={color} opacity={0.22} />
          <circle cx={tip.x} cy={tip.y} r={width * 1.3} fill={color} />
        </>
      )}
    </svg>
  );
};

export const P = (id: NodeId): Pt => ({ x: NODES[id].x, y: NODES[id].y });

/** Agent 走出来的那张网（定格用） */
export const WEB: Pt[][] = [
  [P("finder"), P("safari"), P("mail"), P("terminal")],
  [P("terminal"), P("messages")],
  [P("finder"), P("terminal")],
  [P("safari"), P("messages")],
  [P("mail"), P("finder")],
];

export const Web: React.FC<{ progress: number; opacity?: number; width?: number }> = ({ progress, opacity = 1, width = 8 }) => (
  <>
    {WEB.map((pts, i) => (
      <Path key={i} pts={pts} progress={Math.max(0, Math.min(1, progress * WEB.length - i))} head={false} width={width} opacity={opacity} />
    ))}
  </>
);
