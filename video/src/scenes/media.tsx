import React from "react";
import { AbsoluteFill, Easing, interpolate, useCurrentFrame } from "remotion";
import { layout, theme } from "../theme";
import { Shot } from "../types";
import { AssetVisual, Enter, Label, ScreenshotViewport, SourceCredit, useShotFrames } from "../ui";

const STAGE_W = 1080 - layout.side * 2;
const BAR = 78;

const domainOf = (url?: string, fallback = "") => {
  try {
    return url ? new URL(url).hostname.replace(/^www\./, "") : fallback;
  } catch {
    return fallback;
  }
};

const Card: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Enter style={{ position: "absolute", left: layout.side, top: layout.stageTop, width: STAGE_W, height: layout.stageHeight }}>
    <div style={{ width: "100%", height: "100%", borderRadius: 30, overflow: "hidden", border: `2px solid ${theme.border}`, background: theme.surface, boxShadow: "0 30px 80px rgba(0,0,0,0.55)" }}>
      {children}
    </div>
  </Enter>
);

/** 网页截图放在浏览器外框里：显示域名，滚动到要强调的段落 */
export const BrowserScreenshotScene: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frames = useShotFrames(shot);
  if (!shot.asset) return null;
  return (
    <AbsoluteFill>
      <Label headline={shot.headline} sub={shot.sub} />
      <Card>
        <div style={{ height: BAR, background: theme.surfaceHi, display: "flex", alignItems: "center", padding: "0 26px", gap: 18, borderBottom: `2px solid ${theme.border}` }}>
          <div style={{ display: "flex", gap: 10 }}>
            {[0, 1, 2].map((i) => <div key={i} style={{ width: 16, height: 16, borderRadius: 8, background: theme.border }} />)}
          </div>
          <div style={{ flex: 1, height: 46, borderRadius: 23, background: theme.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 28, color: theme.muted }}>
            {domainOf(shot.asset.url, shot.asset.source)}
          </div>
        </div>
        <ScreenshotViewport asset={shot.asset} highlight={shot.highlight} width={STAGE_W - 4} height={layout.stageHeight - BAR - 4} durationInFrames={frames} maxZoom={1.28} />
      </Card>
      <SourceCredit source={shot.asset.source} />
    </AbsoluteFill>
  );
};

/** 系统或应用的真实界面放在桌面窗口外框里 */
export const PhoneOrDesktopScene: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frames = useShotFrames(shot);
  if (!shot.asset) return null;
  return (
    <AbsoluteFill>
      <Label headline={shot.headline} sub={shot.sub} />
      <Card>
        <div style={{ height: BAR, background: "#ececec", display: "flex", alignItems: "center", padding: "0 26px", gap: 12, borderBottom: "2px solid #d6d6d6" }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 20, height: 20, borderRadius: 10, background: c }} />)}
          <div style={{ flex: 1, textAlign: "center", fontSize: 28, color: "#555", fontWeight: 600, marginRight: 84 }}>系统设置</div>
        </div>
        <ScreenshotViewport asset={shot.asset} highlight={shot.highlight} width={STAGE_W - 4} height={layout.stageHeight - BAR - 4} durationInFrames={frames} maxZoom={1.35} />
      </Card>
      <SourceCredit source={shot.asset.source} />
    </AbsoluteFill>
  );
};

/** 视频按原比例播放；静态图片缓慢推近。 */
export const RealMediaScene: React.FC<{ shot: Shot }> = ({ shot }) => {
  const frame = useCurrentFrame();
  const durationInFrames = useShotFrames(shot);
  if (!shot.asset) return null;
  return (
    <AbsoluteFill>
      <Label headline={shot.headline} sub={shot.sub} />
      <Card>
        <AssetVisual
          asset={shot.asset}
          fit={shot.asset.type === "autoclip_video" ? "contain" : "cover"}
          style={shot.asset.type === "autoclip_video" ? undefined : {
            scale: interpolate(frame, [0, durationInFrames], [1.02, 1.12], { extrapolateRight: "clamp", easing: Easing.linear }),
          }}
        />
      </Card>
      <SourceCredit source={shot.asset.source} />
    </AbsoluteFill>
  );
};
