import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions } from "./Captions";
import { ConceptDiagramScene } from "./scenes/diagram";
import { BrowserScreenshotScene, PhoneOrDesktopScene, RealMediaScene } from "./scenes/media";
import { ConclusionScene, DataScene, HookScene, QuoteScene } from "./scenes/text";
import { theme } from "./theme";
import { Shot, VideoProps } from "./types";

const renderShot = (shot: Shot, sources: string[]) => {
  switch (shot.component) {
    case "HookScene": return <HookScene shot={shot} />;
    case "RealMediaScene": return <RealMediaScene shot={shot} />;
    case "BrowserScreenshotScene": return <BrowserScreenshotScene shot={shot} />;
    case "PhoneOrDesktopScene": return <PhoneOrDesktopScene shot={shot} />;
    case "DataScene": return <DataScene shot={shot} />;
    case "ConceptDiagramScene": return <ConceptDiagramScene shot={shot} />;
    case "QuoteScene": return <QuoteScene shot={shot} />;
    case "ConclusionScene": return <ConclusionScene shot={shot} sources={sources} />;
    default: return <HookScene shot={shot} />;
  }
};

const Progress: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: 0, top: 0, width: "100%", height: 8, background: theme.surfaceHi }}>
      <div style={{ height: "100%", background: theme.accent, width: `${interpolate(frame, [0, durationInFrames], [0, 100], { extrapolateRight: "clamp" })}%` }} />
    </div>
  );
};

export const TrendVideo: React.FC<VideoProps> = ({ scenes, captions, audio, sources }) => {
  const { fps, durationInFrames } = useVideoConfig();
  const shots = scenes.flatMap((scene) => scene.shots.map((shot) => ({ scene, shot })));
  return (
    <AbsoluteFill style={{ background: theme.bg, fontFamily: theme.font, color: theme.text }}>
      {shots.map(({ scene, shot }, i) => {
        const from = Math.round(shot.start * fps);
        const next = shots[i + 1];
        // 每个镜头一直持续到下一个镜头开始，中间不留空帧
        const until = next ? Math.round(next.shot.start * fps) : durationInFrames;
        return (
          <Sequence key={i} name={`${scene.scene_id} · ${shot.component}`} from={from} durationInFrames={Math.max(1, until - from)}>
            {renderShot(shot, sources)}
          </Sequence>
        );
      })}
      <Captions pages={captions} />
      <Progress />
      {audio ? <Audio src={staticFile(audio)} /> : null}
    </AbsoluteFill>
  );
};
