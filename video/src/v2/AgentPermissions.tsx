import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Sequence, staticFile, useCurrentFrame } from "remotion";
import { C, FONT, FPS, H, W } from "./kit";
import { S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11 } from "./shotsA";
import { S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22 } from "./shotsB";
import { DirectedProps, ShotProps } from "./types";

const SHOTS: React.FC<ShotProps>[] = [S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18, S19, S20, S21, S22];

/** 给静音观看的人的一行小字幕。不抢画面：小、靠下、半透明底。最后一个镜头收声时不显示。 */
const Subs: React.FC<{ p: DirectedProps }> = ({ p }) => {
  const ms = (useCurrentFrame() / FPS) * 1000;
  const page = p.captions.find((c) => ms >= c.startMs - 40 && ms < c.endMs);
  if (!page) return null;
  return (
    <div style={{ position: "absolute", left: 0, width: W, top: 1590, display: "flex", justifyContent: "center" }}>
      <div style={{ fontSize: 42, fontWeight: 600, color: "#fff", background: "rgba(0,0,0,0.62)", padding: "10px 26px", borderRadius: 14, letterSpacing: 1 }}>{page.text}</div>
    </div>
  );
};

/** 音效都是自己合成的，音量压得很低，只在有真实动作的地方出现 */
const sfx = (p: DirectedProps) => {
  const at = (id: number, offset = 0) => p.shots[id - 1].start + offset;
  return [
    { src: "click.wav", t: at(1, 0.45), v: 0.9 },
    ...[0.0, 0.32, 0.64, 1.0, 1.36, 1.72].map((o) => ({ src: "key.wav", t: at(2, (o * (p.shots[1].end - p.shots[1].start)) / 2.3), v: 0.7 })),
    { src: "whoosh.wav", t: at(3, 0.0), v: 0.4 },
    { src: "click.wav", t: at(4, 1.4), v: 0.7 },
    { src: "hit.wav", t: at(5, 1.6), v: 0.6 },
    { src: "click.wav", t: at(8, 0.9), v: 0.6 },
    { src: "hit.wav", t: at(11, 2.2), v: 0.45 },
    { src: "whoosh.wav", t: at(12, 1.25), v: 0.4 },
    { src: "hit.wav", t: at(13, 0.22), v: 0.55 },
    { src: "whoosh.wav", t: at(14, 0.4), v: 0.35 },
    { src: "whoosh.wav", t: at(16, 2.2), v: 0.35 },
    { src: "hit.wav", t: at(19, 0.2), v: 0.5 },
    { src: "whoosh.wav", t: at(20, 0.0), v: 0.5 },
  ];
};

export const AgentPermissions: React.FC<DirectedProps> = (p) => {
  const total = Math.ceil(p.duration * FPS);
  return (
    <AbsoluteFill style={{ background: C.space, fontFamily: FONT, color: C.text, width: W, height: H }}>
      {p.shots.map((s, i) => {
        const Shot = SHOTS[i];
        const from = Math.round(s.start * FPS);
        const until = i + 1 < p.shots.length ? Math.round(p.shots[i + 1].start * FPS) : total;
        return (
          <Sequence key={s.id} name={`${String(s.id).padStart(2, "0")}`} from={from} durationInFrames={Math.max(1, until - from)}>
            <Shot s={s} p={p} />
          </Sequence>
        );
      })}
      <Subs p={p} />
      <Audio src={staticFile("audio/voice.wav")} />
      {sfx(p).map((e, i) => (
        <Sequence key={i} from={Math.max(0, Math.round(e.t * FPS))} durationInFrames={30} layout="none">
          <Audio src={staticFile(`audio/sfx/${e.src}`)} volume={e.v} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
