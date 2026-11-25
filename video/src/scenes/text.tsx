import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { layout, theme } from "../theme";
import { Shot } from "../types";
import { AssetVisual, Enter, Stage } from "../ui";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

/** 大字。让浏览器自己均衡换行，不会在词中间留下一两个字的尾巴。从第一帧就可见。 */
const BigText: React.FC<{ text: string; size: number; color?: string }> = ({ text, size, color = theme.text }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        fontSize: size, fontWeight: 800, color, lineHeight: 1.22, letterSpacing: 2, textWrap: "balance",
        opacity: interpolate(frame, [0, 5], [0.35, 1], { extrapolateRight: "clamp" }),
        translate: interpolate(frame, [0, 14], ["0px 30px", "0px 0px"], { extrapolateRight: "clamp", easing: ease }),
      }}
    >
      {/* 标题里有 "A / B"、"A，B" 这样的分隔时，按分隔换行，不在词中间断开 */}
      {text.split(/\s*[/／|｜，,：:]\s*/).filter(Boolean).map((line, i) => (
        <div key={i} style={{ whiteSpace: line.length * size <= 960 ? "nowrap" : "normal" }}>{line}</div>
      ))}
    </div>
  );
};

// 字号按最长的一行决定
const sizeFor = (text: string, big: number) => {
  const longest = Math.max(...text.split(/\s*[/／|｜，,：:]\s*/).map((l) => l.length), 1);
  return longest <= 5 ? big : longest <= 7 ? big * 0.72 : longest <= 9 ? big * 0.56 : big * 0.46;
};

const Backdrop: React.FC<{ shot: Shot }> = ({ shot }) =>
  shot.asset ? (
    <AbsoluteFill>
      <AssetVisual asset={shot.asset} fit="cover" style={{ objectPosition: "top", opacity: 0.2, filter: "grayscale(1)" }} />
      <AbsoluteFill style={{ background: "linear-gradient(180deg, rgba(12,12,11,0.5) 0%, rgba(12,12,11,0.96) 62%)" }} />
    </AbsoluteFill>
  ) : null;

export const HookScene: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Backdrop shot={shot} />
      <div style={{ position: "absolute", left: layout.side, right: layout.side, top: 430 }}>
        <div style={{ width: interpolate(frame, [0, 14], [40, 140], { extrapolateRight: "clamp", easing: ease }), height: 12, borderRadius: 6, background: theme.accent, marginBottom: 50 }} />
        <BigText text={shot.headline} size={sizeFor(shot.headline, 190)} />
        {shot.sub && <Enter delay={8} style={{ fontSize: 50, color: theme.muted, marginTop: 44 }}>{shot.sub}</Enter>}
      </div>
    </AbsoluteFill>
  );
};

export const ConclusionScene: React.FC<{ shot: Shot; sources: string[] }> = ({ shot, sources }) => (
  <AbsoluteFill>
    <Backdrop shot={shot} />
    <Stage>
      <div style={{ width: 140, height: 12, borderRadius: 6, background: theme.accent, marginBottom: 50 }} />
      <BigText text={shot.headline} size={sizeFor(shot.headline, 180)} />
      {shot.sub && <Enter delay={6} style={{ fontSize: 50, color: theme.accent, marginTop: 44, fontWeight: 600 }}>{shot.sub}</Enter>}
      {sources.length > 0 && (
        <div style={{ position: "absolute", left: 46, right: 46, bottom: 40, fontSize: 28, color: theme.faint, lineHeight: 1.5 }}>
          来源：{sources.join(" · ")}
        </div>
      )}
    </Stage>
  </AbsoluteFill>
);

export const DataScene: React.FC<{ shot: Shot }> = ({ shot }) => (
  <AbsoluteFill>
    <Stage>
      {shot.headline && <div style={{ fontSize: 46, color: theme.muted, marginBottom: 30 }}>{shot.headline}</div>}
      <BigText text={shot.data.value} size={sizeFor(shot.data.value, 230)} color={theme.accent} />
      <Enter delay={6} style={{ fontSize: 54, color: theme.text, marginTop: 36, fontWeight: 600, lineHeight: 1.35 }}>{shot.data.label}</Enter>
    </Stage>
  </AbsoluteFill>
);

export const QuoteScene: React.FC<{ shot: Shot }> = ({ shot }) => (
  <AbsoluteFill>
    <Stage>
      <div style={{ fontSize: 220, lineHeight: 0.7, color: theme.accent, fontWeight: 800, height: 130 }}>“</div>
      <Enter style={{ fontSize: 72, fontWeight: 700, color: theme.text, lineHeight: 1.38, textWrap: "balance" }}>{shot.quote.text}</Enter>
      <Enter delay={8} style={{ fontSize: 40, color: theme.muted, marginTop: 44 }}>—— {shot.quote.attribution}</Enter>
    </Stage>
  </AbsoluteFill>
);
