import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { theme } from "../theme";
import { Shot } from "../types";
import { Stage, useShotFrames } from "../ui";

const ease = Easing.bezier(0.16, 1, 0.3, 1);

/** 图解里的元素按镜头时长分批出现，保证镜头结束前全部出完 */
const useStagger = (count: number, frames: number) => {
  // 全部元素在镜头前 45% 的时间里出完，后面留给观众看
  const usable = Math.min(frames * 0.45, count * 9);
  return (i: number) => 2 + (count <= 1 ? 0 : (usable * i) / count);
};

const Chip: React.FC<{ text: string; delay: number; accent?: boolean; big?: boolean }> = ({ text, delay, accent, big }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        padding: big ? "32px 36px" : "26px 26px", borderRadius: 22, fontSize: big ? 56 : 46, fontWeight: 650, lineHeight: 1.25,
        color: accent ? theme.bg : theme.text, background: accent ? theme.accent : theme.surfaceHi,
        border: `2px solid ${accent ? theme.accent : theme.border}`,
        opacity: interpolate(frame, [delay, delay + 8], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        scale: interpolate(frame, [delay, delay + 14], [0.9, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease, output: "perceptual-scale" }),
      }}
    >
      {text}
    </div>
  );
};

const Compare: React.FC<{ shot: Shot; frames: number }> = ({ shot, frames }) => {
  const d = shot.diagram;
  const at = useStagger(d.left_items.length + d.right_items.length + 2, frames);
  const column = (label: string, items: string[], offset: number, accent: boolean) => (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ fontSize: 44, fontWeight: 700, color: accent ? theme.accent : theme.muted, marginBottom: 6 }}>{label}</div>
      {items.map((it, i) => <Chip key={i} text={it} delay={at(offset + i)} />)}
    </div>
  );
  return (
    <div style={{ display: "flex", gap: 26, alignItems: "stretch" }}>
      <div style={{ flex: 1, padding: 28, borderRadius: 26, border: `2px solid ${theme.border}`, background: theme.bg }}>
        {column(d.left_label, d.left_items, 0, false)}
      </div>
      <div style={{ flex: 1, padding: 28, borderRadius: 26, border: `3px solid ${theme.accent}`, background: theme.bg }}>
        {column(d.right_label, d.right_items, d.left_items.length, true)}
      </div>
    </div>
  );
};

const Flow: React.FC<{ shot: Shot; frames: number }> = ({ shot, frames }) => {
  const frame = useCurrentFrame();
  const steps = shot.diagram.steps;
  const at = useStagger(steps.length, frames);
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "stretch", gap: 0 }}>
      {steps.map((s, i) => (
        <React.Fragment key={i}>
          {i > 0 && (
            <div style={{ alignSelf: "center", width: 6, height: 54, background: theme.border, margin: "10px 0",
              opacity: interpolate(frame, [at(i) - 4, at(i) + 4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }} />
          )}
          <Chip text={s} delay={at(i)} accent={i === steps.length - 1} big />
        </React.Fragment>
      ))}
    </div>
  );
};

const Grid: React.FC<{ shot: Shot; frames: number }> = ({ shot, frames }) => {
  const items = shot.diagram.steps;
  const at = useStagger(items.length, frames);
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
      {items.map((s, i) => <Chip key={i} text={s} delay={at(i)} big />)}
    </div>
  );
};

/** 解释概念的图解：左右对比 / 步骤推进 / 并列的一组东西 */
export const ConceptDiagramScene: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frames = useShotFrames(shot);
  const d = shot.diagram;
  const title = d.title || shot.headline;
  return (
    <AbsoluteFill>
      <Stage>
        {title && <div style={{ fontSize: 68, fontWeight: 800, color: theme.text, marginBottom: shot.sub ? 14 : 50, lineHeight: 1.25, textWrap: "balance" }}>{title}</div>}
        {shot.sub && <div style={{ fontSize: 36, color: theme.muted, marginBottom: 50 }}>{shot.sub}</div>}
        {d.kind === "compare" && <Compare shot={shot} frames={frames} />}
        {d.kind === "flow" && <Flow shot={shot} frames={frames} />}
        {d.kind === "grid" && <Grid shot={shot} frames={frames} />}
      </Stage>
    </AbsoluteFill>
  );
};
