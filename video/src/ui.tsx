import { Video } from "@remotion/media";
import React from "react";
import { Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { layout, theme } from "./theme";
import { Asset, Box } from "./types";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

/** 镜头的 Sequence 裁掉超出的片段；较短的片段在镜头内循环。保留原有口播音轨。 */
export const AssetVisual: React.FC<{
  asset: Asset; fit: "cover" | "contain"; style?: React.CSSProperties;
}> = ({ asset, fit, style }) => {
  const src = staticFile(asset.path);
  const size = { width: "100%", height: "100%", ...style };
  return asset.type === "autoclip_video"
    ? <Video src={src} muted loop objectFit={fit} style={size} />
    : <Img src={src} style={{ ...size, objectFit: fit }} />;
};

/** 每个镜头的入场：很快的淡入 + 轻微上移。CSS transition 在渲染时不生效，所以全部用帧驱动。 */
export const Enter: React.FC<{ children: React.ReactNode; delay?: number; distance?: number; style?: React.CSSProperties }> = ({
  children, delay = 0, distance = 28, style,
}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        ...style,
        opacity: interpolate(frame, [delay, delay + 5], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        translate: interpolate(frame, [delay, delay + 14], [`0px ${distance}px`, "0px 0px"], {
          extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease,
        }),
      }}
    >
      {children}
    </div>
  );
};

/** 画面顶部的短标签：点明观众正在看什么 */
export const Label: React.FC<{ headline: string; sub?: string }> = ({ headline, sub }) => {
  if (!headline && !sub) return null;
  return (
    <Enter style={{ position: "absolute", left: layout.side, right: layout.side, top: layout.labelTop }} distance={16}>
      {headline && (
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
          <div style={{ width: 10, height: 44, borderRadius: 5, background: theme.accent }} />
          <div style={{ fontSize: 50, fontWeight: 700, color: theme.text, letterSpacing: 1 }}>{headline}</div>
        </div>
      )}
      {sub && <div style={{ fontSize: 34, color: theme.muted, marginTop: 10, marginLeft: headline ? 28 : 0 }}>{sub}</div>}
    </Enter>
  );
};

/** 文字和图解镜头的底板：和真实素材的卡片在同一个位置，画面不会突然变成一片空的黑底 */
export const Stage: React.FC<{ children: React.ReactNode; top?: number; height?: number }> = ({ children, top = layout.stageTop - 90, height = layout.stageHeight + 90 }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute", left: layout.side, right: layout.side, top, height,
        borderRadius: 30, border: `2px solid ${theme.border}`, background: theme.surface,
        padding: "0 46px", display: "flex", flexDirection: "column", justifyContent: "center",
        opacity: interpolate(frame, [0, 3], [0.6, 1], { extrapolateRight: "clamp" }),
      }}
    >
      {children}
    </div>
  );
};

export const SourceCredit: React.FC<{ source: string }> = ({ source }) => (
  <div style={{ position: "absolute", left: layout.side + 8, top: layout.stageTop + layout.stageHeight + 18, fontSize: 28, color: theme.faint }}>
    来源：{source}
  </div>
);

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** 一个镜头有多少帧 */
export const useShotFrames = (shot: { start: number; end: number }) => {
  const { fps } = useVideoConfig();
  return Math.max(1, Math.round((shot.end - shot.start) * fps));
};

/**
 * 一张（通常很长的）截图在固定视窗里：滚动并推近到要强调的那几行，再把它框出来。
 * 图片始终按原始比例缩放，不会被拉伸。
 */
export const ScreenshotViewport: React.FC<{
  asset: Asset; highlight: Box | null; width: number; height: number; durationInFrames: number; maxZoom?: number;
}> = ({ asset, highlight, width, height, durationInFrames, maxZoom = 1.5 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const base = width / asset.width;            // 缩放到视窗宽度
  const W = width, H = asset.height * base;

  // 目标状态：把高亮区域放到视窗偏上的位置；没有高亮就从页面顶部慢慢往下滚
  const zoom = highlight ? clamp((width * 0.86) / Math.max(highlight.w * W, 1), 1, maxZoom) : 1;
  const fx = highlight ? (highlight.x + highlight.w / 2) * W : W / 2;
  const fy = highlight ? (highlight.y + highlight.h / 2) * H : 0;
  const settle = Math.min(1.1 * fps, durationInFrames * 0.5);
  const p = interpolate(frame, [0, settle], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });
  const drift = interpolate(frame, [0, durationInFrames], [0, 1], { extrapolateRight: "clamp" });

  const s = highlight ? 1 + (zoom - 1) * p + 0.03 * drift : 1 + 0.02 * drift;
  const startY = highlight ? Math.max(0, fy - height * 0.9) : 0;   // 从目标上方一点开始滚
  const focusY = highlight ? startY + (fy - startY) * p : 0;
  const x = clamp(width / 2 - fx * s, Math.min(0, width - W * s), 0);
  const y = highlight
    ? clamp(height * 0.4 - focusY * s, Math.min(0, height - H * s), 0)
    : -Math.min(Math.max(0, H * s - height), 260) * drift;

  const pad = 14;
  return (
    <div style={{ width, height, overflow: "hidden", position: "relative", background: "#fff" }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, transformOrigin: "0 0", transform: `translate(${x}px, ${y}px) scale(${s})` }}>
        <Img src={staticFile(asset.path)} style={{ width: W, height: H, display: "block" }} />
        {highlight && (
          <div
            style={{
              position: "absolute",
              left: highlight.x * W - pad, top: highlight.y * H - pad,
              width: highlight.w * W + pad * 2, height: highlight.h * H + pad * 2,
              borderRadius: 12, border: `5px solid ${theme.accent}`, background: "rgba(245, 184, 61, 0.16)",
              boxShadow: "0 0 0 2000px rgba(0, 0, 0, 0.28)",   // 把高亮以外的部分压暗一点
              opacity: interpolate(frame, [settle * 0.55, settle * 0.55 + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
            }}
          />
        )}
      </div>
    </div>
  );
};
