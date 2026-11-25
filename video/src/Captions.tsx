import React from "react";
import { Easing, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { layout, theme } from "./theme";
import { CaptionPage } from "./types";

/**
 * 字幕：每屏一小句，中文大字。时间来自 TTS 的逐词时间戳。
 * 重点词用强调色；还没念到的词稍微暗一点，念到时亮起来。
 */
export const Captions: React.FC<{ pages: CaptionPage[] }> = ({ pages }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const page = pages.find((p) => ms >= p.startMs - 40 && ms < p.endMs);
  if (!page) return null;

  // 哪些字属于重点词
  const emphasized = new Array(page.text.length).fill(false);
  for (const word of page.emphasis) {
    let from = page.text.indexOf(word);
    while (from >= 0) {
      for (let i = from; i < from + word.length; i++) emphasized[i] = true;
      from = page.text.indexOf(word, from + word.length);
    }
  }

  const startFrame = (page.startMs / 1000) * fps;
  const size = page.text.length > 11 ? 66 : 76;
  let cursor = 0;
  return (
    <div
      style={{
        position: "absolute", left: layout.side, right: layout.side, top: layout.captionCenter - 110, height: 220,
        display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center",
        opacity: interpolate(frame, [startFrame - 1, startFrame + 3], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
        scale: interpolate(frame, [startFrame - 1, startFrame + 6], [0.95, 1], {
          extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1), output: "perceptual-scale",
        }),
      }}
    >
      <div style={{ fontSize: size, fontWeight: 800, lineHeight: 1.28, letterSpacing: 1, textShadow: "0 4px 24px rgba(0,0,0,0.9), 0 0 3px rgba(0,0,0,0.9)" }}>
        {page.tokens.map((token, ti) => {
          const begin = cursor;
          cursor += token.text.length;
          const spoken = ms >= token.startMs - 60;
          return (
            <span key={ti} style={{ opacity: spoken ? 1 : 0.5 }}>
              {token.text.split("").map((ch, ci) => (
                <span key={ci} style={{ color: emphasized[begin + ci] ? theme.accent : theme.text }}>{ch}</span>
              ))}
            </span>
          );
        })}
      </div>
    </div>
  );
};
