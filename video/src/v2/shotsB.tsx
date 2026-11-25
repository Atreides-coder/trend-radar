import React from "react";
import { AbsoluteFill, Easing, Img, staticFile } from "remotion";
import { Badge, Box, C, Cam, Cursor, E_IN, E_IO, E_OUT, FONT, H, Keyword, lerp, MONO, Plate, Scrim, Toggle, useT, W } from "./kit";
import { Node, P, Path, Web } from "./map";
import { wordAt } from "./shotsA";
import { BoxT, ShotProps } from "./types";

const dur = (s: ShotProps["s"]) => s.end - s.start;
const PAGE = { w: 1080, h: 3000 };
const px = (b: BoxT) => (b ? { x: b.x * PAGE.w, y: b.y * PAGE.h, w: b.w * PAGE.w, h: b.h * PAGE.h } : { x: 100, y: 600, w: 800, h: 60 });
const center = (b: BoxT) => { const r = px(b); return { x: r.x + r.w / 2, y: r.y + r.h / 2 }; };
/** 推近到一个区域时最多放多大，保证这个区域完整留在画面里 */
const fit = (b: BoxT, max = 1.6) => Math.max(1, Math.min(max, 1000 / (px(b).w + 40)));

const Source: React.FC<{ text: string; dark?: boolean }> = ({ text }) => (
  <div style={{ position: "absolute", left: 48, top: 150, fontSize: 28, padding: "8px 18px", borderRadius: 10, color: "#fff", background: "rgba(0,0,0,0.72)", letterSpacing: 1 }}>
    来源：{text}
  </div>
);

/** 12 · 地图上“信息”被碰到 → 冲进报道，推近到用户说法 */
export const S12: React.FC<ShotProps> = ({ s, p }) => {
  const t = useT();
  const cut = Math.min(1.3, dur(s) * 0.36);
  const c = center(p.boxes.ars_user);
  const b = px(p.boxes.ars_user);
  if (t < cut) {
    return (
      <AbsoluteFill style={{ background: C.space }}>
        <Web progress={1} opacity={0.55} />
        <Path pts={[P("terminal"), P("messages")]} progress={lerp(t, [0.1, 0.55], [0, 1], E_IO)} color={C.red} />
        {(["finder", "safari", "mail", "terminal"] as const).map((id) => <Node key={id} id={id} opacity={0.7} />)}
        <Node id="messages" ring={C.red} ringAt={0.5} size={190} />
      </AbsoluteFill>
    );
  }
  const u = t - cut;
  return (
    <AbsoluteFill style={{ background: "#e9e9e6" }}>
      <div style={{ position: "absolute", inset: 0, translate: `0px ${lerp(u, [0, 0.22], [900, 0])}px` }}>
        <Cam w={PAGE.w} h={PAGE.h} ay={H * 0.42} keys={[{ t: cut, x: 540, y: 520, z: 1 }, { t: cut + 0.3, x: 540, y: 520, z: 1 }, { t: cut + 0.85, x: c.x, y: c.y, z: fit(p.boxes.ars_user) }, { t: dur(s), x: c.x, y: c.y + 20, z: fit(p.boxes.ars_user) * 1.05 }]}>
          <Plate src="assets/source_1_page.png" w={PAGE.w} h={PAGE.h} />
          <Box x={b.x} y={b.y} w={b.w} h={b.h} at={cut + 0.75} />
        </Cam>
      </div>
      <Scrim top={1000} />
      <Source text="Ars Technica" />
      <Keyword text="用户说：没授权" at={cut + 0.95} y={1200} size={104} color="#fff" />
    </AbsoluteFill>
  );
};

/** 13 · 两句原文对撞：用户说 / Meta 说 */
export const S13: React.FC<ShotProps> = ({ p }) => {
  const t = useT();
  const strip = (b: BoxT, top: number, from: number, label: string, color: string) => {
    const r = px(b);
    const z = fit(b, 1.3);
    const slide = lerp(t, [0, 0.24], [from, 0]);
    return (
      <div style={{ position: "absolute", left: 0, top, width: W, height: 470, overflow: "hidden", translate: `${slide}px 0px`, borderTop: `6px solid ${color}`, borderBottom: `6px solid ${color}` }}>
        <div style={{ position: "absolute", left: 0, top: 0, width: PAGE.w, height: PAGE.h, transformOrigin: "0 0",
          transform: `translate(${W / 2 - (r.x + r.w / 2) * z}px, ${250 - (r.y + r.h / 2) * z}px) scale(${z})` }}>
          <Plate src="assets/source_1_page.png" w={PAGE.w} h={PAGE.h} />
          <div style={{ position: "absolute", left: r.x - 8, top: r.y - 8, width: r.w + 16, height: r.h + 16, borderRadius: 10, border: `4px solid ${color}`, background: "rgba(245,184,61,0.2)" }} />
        </div>
        <div style={{ position: "absolute", left: 40, top: 26, fontSize: 44, fontWeight: 800, padding: "10px 26px", borderRadius: 14, background: color, color: "#111" }}>{label}</div>
      </div>
    );
  };
  return (
    <AbsoluteFill style={{ background: C.space }}>
      {strip(p.boxes.ars_user, 290, -W, "用户", C.amber)}
      {strip(p.boxes.ars_meta, 960, W, "Meta", "#e8e7e1")}
      <div style={{ position: "absolute", left: 0, width: W, top: 800, textAlign: "center", fontSize: 96, fontWeight: 800, color: C.text, letterSpacing: 10,
        opacity: lerp(t, [0.26, 0.4], [0, 1]), scale: `${lerp(t, [0.26, 0.5], [1.5, 1])}` }}>各执一词</div>
      <Source text="Ars Technica" />
    </AbsoluteFill>
  );
};

const ApplePage: React.FC<{ keys: { t: number; x: number; y: number; z: number }[]; children?: React.ReactNode; drop?: number }> = ({ keys, children, drop }) => {
  const t = useT();
  return (
    <div style={{ position: "absolute", inset: 0, translate: drop === undefined ? undefined : `0px ${lerp(t, [drop, drop + 0.26], [1500, 0])}px` }}>
      <Cam w={PAGE.w} h={PAGE.h} ay={H * 0.42} keys={keys}>
        <Plate src="assets/source_3_page.png" w={PAGE.w} h={PAGE.h} />
        {children}
      </Cam>
    </div>
  );
};

/** 14 · 地址栏打出苹果开发者网站，页面落下，冲向日期 */
export const S14: React.FC<ShotProps> = ({ s, p }) => {
  const t = useT();
  const url = "developer.apple.com/news";
  const typed = url.slice(0, Math.floor(lerp(t, [0.05, 0.5], [0, url.length], Easing.linear)));
  const d = px(p.boxes.apple_date);
  const c = center(p.boxes.apple_date);
  return (
    <AbsoluteFill style={{ background: "#fff" }}>
      <ApplePage drop={0.45} keys={[{ t: 0.45, x: 540, y: 620, z: 1 }, { t: 0.8, x: 540, y: 660, z: 1 }, { t: dur(s) - 0.1, x: c.x + 150, y: c.y - 30, z: 2.1 }]}>
        <Box x={d.x} y={d.y} w={d.w} h={d.h} at={Math.max(0.9, dur(s) - 0.7)} pad={8} dim={false} />
      </ApplePage>
      <div style={{ position: "absolute", left: 60, right: 60, top: 150, height: 96, borderRadius: 48, background: "#f1f1f3", border: "2px solid #d9d9de",
        display: "flex", alignItems: "center", padding: "0 40px", fontSize: 44, color: "#111", fontFamily: MONO, boxShadow: "0 10px 40px rgba(0,0,0,0.18)" }}>
        <span style={{ color: "#8a8a8f", marginRight: 16 }}>🔒</span>{typed}<span style={{ opacity: t < 0.55 ? 1 : 0, color: C.amber }}>|</span>
      </div>
    </AbsoluteFill>
  );
};

/** 15 · 推近到原句：very explicit user action */
export const S15: React.FC<ShotProps> = ({ s, p }) => {
  const t = useT();
  const from = center(p.boxes.apple_date), b = px(p.boxes.apple_explicit), c = center(p.boxes.apple_explicit);
  // 这一行是 “do so with very explicit user action. Addressing this”，要强调的是中间那几个词
  const hx = b.x + b.w * 0.2, hw = b.w * 0.5;
  return (
    <AbsoluteFill style={{ background: "#fff" }}>
      <ApplePage keys={[{ t: 0, x: from.x + 150, y: from.y - 30, z: 2.1 }, { t: 0.5, x: c.x, y: c.y, z: 1.36 }, { t: dur(s), x: hx + hw / 2, y: c.y, z: 1.62 }]}>
        <Box x={hx} y={b.y} w={hw} h={b.h} at={0.5} pad={7} />
      </ApplePage>
      <Scrim top={960} />
      <Source text="developer.apple.com" />
      <Keyword text="非常明确的用户操作" at={0.85} y={1130} size={96} color="#fff" />
      <div style={{ position: "absolute", left: 0, width: W, top: 1240, textAlign: "center", fontSize: 40, color: "rgba(255,255,255,0.75)", fontFamily: MONO,
        opacity: lerp(t, [1.0, 1.25], [0, 1]) }}>very explicit user action</div>
    </AbsoluteFill>
  );
};

/** 16 · 苹果的理由：autonomous —— 这个词被拎出来，落到地图上 */
export const S16: React.FC<ShotProps> = ({ s, p }) => {
  const t = useT();
  const d = dur(s);
  const from = center(p.boxes.apple_explicit), b = px(p.boxes.apple_agents), c = center(p.boxes.apple_agents);
  const lift = wordAt(s, "自主", d - 1.0) - 0.15;
  const k = lerp(t, [lift, lift + 0.55], [0, 1], E_IO);
  return (
    <AbsoluteFill style={{ background: C.space }}>
      <AbsoluteFill style={{ opacity: lerp(t, [lift + 0.1, lift + 0.5], [1, 0]), background: "#fff" }}>
        <ApplePage keys={[{ t: 0, x: from.x, y: from.y, z: 2.05 }, { t: 0.45, x: c.x, y: c.y, z: fit(p.boxes.apple_agents, 1.3) }, { t: lift, x: c.x, y: c.y, z: fit(p.boxes.apple_agents, 1.3) * 1.04 }, { t: lift + 0.5, x: c.x, y: c.y + 500, z: fit(p.boxes.apple_agents, 1.3) }]}>
          <Box x={b.x} y={b.y} w={b.w} h={b.h} at={0.45} pad={9} />
        </ApplePage>
        <Scrim top={1000} />
        <Source text="developer.apple.com" />
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: lerp(t, [lift + 0.15, lift + 0.6], [0, 1]) }}>
        <Web progress={lerp(t, [lift + 0.2, d], [0.2, 1], Easing.linear)} />
        {(["finder", "safari", "mail", "messages", "terminal"] as const).map((id) => <Node key={id} id={id} opacity={0.9} label={false} />)}
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 0, width: W, top: lerp(t, [lift, lift + 0.55], [H * 0.42 + 6, 300], E_IO), textAlign: "center",
        opacity: lerp(t, [lift - 0.05, lift + 0.1], [0, 1]) }}>
        <span style={{ display: "inline-block", fontSize: 40 + 80 * k, fontWeight: 800, padding: `${6 + 10 * k}px ${14 + 30 * k}px`, borderRadius: 16,
          background: C.amber, color: "#111", fontFamily: k < 0.5 ? MONO : FONT }}>{k < 0.5 ? "autonomous" : "自主"}</span>
      </div>
      <Keyword text="越来越能干" at={wordAt(s, "能干", 1.4) - 0.05} out={lift - 0.1} y={1160} size={92} color="#fff" />
    </AbsoluteFill>
  );
};

/** 17 · 真实界面：光标悬着，新的确认长什么样还没公布 */
export const S17: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const blink = 0.45 + 0.55 * Math.abs(Math.sin(t * 6));
  return (
    <AbsoluteFill style={{ background: C.ui }}>
      <Cam w={986} h={1668} ay={H * 0.42} keys={[{ t: 0, x: 700, y: 380, z: 1.9 }, { t: dur(s), x: 720, y: 390, z: 2.05 }]}>
        <Plate src="assets/fda_pane.png" w={986} h={1668} />
        <div style={{ position: "absolute", left: 0, top: 374, width: 986, height: 1300, background: "rgba(253,253,253,0.7)" }} />
        <div style={{ position: "absolute", left: 0, top: 0, width: 986, height: 294, background: "rgba(253,253,253,0.7)" }} />
        <Toggle x={855} y={312} w={70} h={44} on={0} />
        <div style={{ position: "absolute", left: 500, top: 410, width: 400, height: 250, borderRadius: 22, border: `5px dashed ${C.amber}`, opacity: blink,
          display: "grid", placeItems: "center", fontSize: 150, fontWeight: 800, color: C.amber, background: "rgba(255,255,255,0.55)" }}>?</div>
        <Cursor x={lerp(t, [0, 0.8], [960, 905])} y={lerp(t, [0, 0.8], [470, 352])} scale={0.6} />
      </Cam>
      <Keyword text="细节未公布" at={0.35} x={70} y={H * 0.42 + 640} size={112} color="#111" align="left" shadow={false} />
    </AbsoluteFill>
  );
};

const Dialog: React.FC<{ children: React.ReactNode; rotY: number; rotX?: number; scale?: number; y?: number }> = ({ children, rotY, rotX = 5, scale = 1, y = 520 }) => (
  <div style={{ position: "absolute", left: 0, top: 0, width: W, height: H, perspective: 1800 }}>
    <div style={{ position: "absolute", left: 130, top: y, width: 820, borderRadius: 44, background: "rgba(246,246,246,0.97)", padding: "56px 50px 44px",
      boxShadow: "0 60px 140px rgba(0,0,0,0.55)", transform: `rotateY(${rotY}deg) rotateX(${rotX}deg) scale(${scale})`, textAlign: "center", color: "#111" }}>
      <Img src={staticFile("assets/icon_terminal.png")} style={{ width: 130, height: 130 }} />
      <div style={{ fontSize: 34, color: "#666", marginTop: 14 }}>“AI Agent”想要访问你的数据</div>
      {children}
      <div style={{ display: "flex", gap: 22, marginTop: 44 }}>
        <div style={{ flex: 1, padding: "24px 0", borderRadius: 20, background: "#dcdcdc", fontSize: 40, fontWeight: 600 }}>不允许</div>
        <div style={{ flex: 1, padding: "24px 0", borderRadius: 20, background: "#0a84ff", color: "#fff", fontSize: 40, fontWeight: 600 }}>允许</div>
      </div>
    </div>
  </div>
);

const Backdrop: React.FC<{ dark?: number }> = ({ dark = 0.5 }) => (
  <AbsoluteFill style={{ background: C.ui }}>
    <Img src={staticFile("assets/fda_pane.png")} style={{ position: "absolute", left: -180, top: -120, width: 1440, filter: "blur(18px)" }} />
    <AbsoluteFill style={{ background: `rgba(11,11,12,${dark})` }} />
  </AbsoluteFill>
);

/** 18 · 以前的弹窗只问一句：它能看什么 */
export const S18: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const q = wordAt(s, "它", dur(s) - 1.1);
  const text = "它能看什么？";
  return (
    <AbsoluteFill>
      <Backdrop />
      <div style={{ position: "absolute", inset: 0, opacity: lerp(t, [0.05, 0.3], [0, 1]), translate: `0px ${lerp(t, [0.05, 0.5], [120, 0])}px` }}>
        <Dialog rotY={lerp(t, [0, dur(s)], [-16, -9], Easing.linear)}>
          <div style={{ fontSize: 96, fontWeight: 800, marginTop: 30, minHeight: 130 }}>
            {text.slice(0, Math.floor(lerp(t, [q - 0.1, q + 0.55], [0, text.length], Easing.linear)))}
          </div>
        </Dialog>
      </div>
      <Keyword text="问题变了" at={0.15} out={q - 0.5} y={300} size={110} color={C.amber} />
      <Badge text="示意 · 非苹果实际设计" y={1380} x={W / 2 - 170} />
    </AbsoluteFill>
  );
};

/** 19 · 划掉，换成另一句：它会拿去做什么 */
export const S19: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const q = wordAt(s, "它", 1.2);
  const next = "它会拿去做什么？";
  const strike = lerp(t, [0.15, 0.38], [0, 1], E_IN);
  return (
    <AbsoluteFill>
      <Backdrop dark={0.62} />
      <Dialog rotY={lerp(t, [0, dur(s)], [14, 7], Easing.linear)} rotX={3} scale={1.06} y={470}>
        <div style={{ position: "relative", fontSize: 72, fontWeight: 800, marginTop: 30, color: "#9a9a9a", display: "inline-block" }}>
          它能看什么？
          <div style={{ position: "absolute", left: -10, top: "52%", height: 9, width: `calc(${strike * 100}% + 20px)`, background: C.red, borderRadius: 5 }} />
        </div>
        <div style={{ fontSize: 88, fontWeight: 800, marginTop: 18, minHeight: 120 }}>
          {next.slice(0, Math.floor(lerp(t, [q - 0.08, q + 0.75], [0, next.length], Easing.linear))).split("").map((ch, i) => (
            <span key={i} style={{ color: i >= 4 && i <= 6 ? "#c77d00" : "#111" }}>{ch}</span>
          ))}
        </div>
      </Dialog>
      <Badge text="示意 · 非苹果实际设计" y={1410} x={W / 2 - 170} />
    </AbsoluteFill>
  );
};

/** 20 · 拉远：同样的开关出现在很多块屏幕上，每一个后面都有一条线刚开始走 */
export const S20: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const d = dur(s);
  const z = lerp(t, [0, d], [3.4, 1], E_OUT);
  const shapes = [
    { w: 150, h: 300 }, { w: 330, h: 220 }, { w: 150, h: 300 }, { w: 330, h: 220 },
    { w: 330, h: 220 }, { w: 150, h: 300 }, { w: 330, h: 220 }, { w: 150, h: 300 },
    { w: 150, h: 300 }, { w: 330, h: 220 }, { w: 150, h: 300 }, { w: 330, h: 220 },
  ];
  return (
    <AbsoluteFill style={{ background: C.space }}>
      <div style={{ position: "absolute", inset: 0, scale: `${z}`, transformOrigin: "50% 45%" }}>
        {shapes.map((sh, i) => {
          const col = i % 3, row = Math.floor(i / 3);
          const cx = 190 + col * 350, cy = 330 + row * 400;
          const grow = lerp(t, [d * 0.25 + i * 0.04, d], [0, 1], Easing.linear);
          return (
            <div key={i} style={{ position: "absolute", left: cx - sh.w / 2, top: cy - sh.h / 2, width: sh.w, height: sh.h, borderRadius: sh.w < 200 ? 30 : 18,
              border: `3px solid ${i === 4 ? C.amber : "#3b3b3f"}`, background: C.panel }}>
              <div style={{ position: "absolute", left: 14, top: 14, width: 44, height: 26, borderRadius: 13, background: C.green }}>
                <div style={{ position: "absolute", right: 2, top: 2, width: 22, height: 22, borderRadius: 11, background: "#fff" }} />
              </div>
              <svg width={sh.w} height={sh.h} style={{ position: "absolute", left: 0, top: 0 }}>
                <path d={`M20 ${sh.h - 30} L${sh.w * 0.4} ${sh.h * 0.55} L${sh.w * 0.62} ${sh.h * 0.78} L${sh.w - 22} ${sh.h * 0.42}`} fill="none" stroke={C.amber}
                  strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - grow} />
              </svg>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const AllowButton: React.FC<{ t: number; hold: number; dark: number }> = ({ t, hold, dark }) => {
  const cy = lerp(Math.min(t, hold), [0, hold], [1210, 1020], Easing.linear);
  return (
    <AbsoluteFill style={{ background: C.space }}>
      <AbsoluteFill style={{ opacity: 1 - dark }}>
        <Backdrop dark={0.7} />
      </AbsoluteFill>
      <div style={{ position: "absolute", left: 110, top: 720, width: 860, height: 300, borderRadius: 60, overflow: "hidden", background: "#0a84ff",
        boxShadow: `0 0 ${60 + 40 * Math.sin(t * 3)}px rgba(245,184,61,0.35)` }}>
        <div style={{ position: "absolute", left: -110, top: -700, width: W, height: H, scale: "0.9", opacity: 0.9 }}>
          <Web progress={1} width={16} opacity={0.55 + 0.45 * Math.abs(Math.sin(t * 2.2))} />
        </div>
        <div style={{ position: "absolute", inset: 0, background: "rgba(10,132,255,0.62)", backdropFilter: "blur(7px)" }} />
        <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", fontSize: 150, fontWeight: 800, color: "#fff", letterSpacing: 16 }}>允许</div>
      </div>
      <Cursor x={lerp(Math.min(t, hold), [0, hold], [800, 640], Easing.linear)} y={cy} scale={2.2} />
    </AbsoluteFill>
  );
};

/** 21 · 回到开场的构图：光标悬在“允许”上，按钮后面是那张网 */
export const S21: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  return (
    <AbsoluteFill style={{ scale: `${lerp(t, [0, dur(s)], [1, 1.06], Easing.linear)}` }}>
      <AllowButton t={t} hold={dur(s) + 1.2} dark={0} />
    </AbsoluteFill>
  );
};

/** 22 · 按下之前定格，其余沉入黑暗 */
export const S22: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const prev = 3.6;                       // 上一个镜头的大致长度，让光标的位置接得上
  const hold = prev + 1.2;
  return (
    <AbsoluteFill style={{ scale: "1.06" }}>
      <AllowButton t={Math.min(prev + t, hold)} hold={hold} dark={lerp(t, [0.2, 1.3], [0, 1], Easing.linear)} />
      <Keyword text="你批准的是什么？" at={wordAt(s, "决定", dur(s) - 1.2) - 0.3} y={480} size={104} color={C.amber} />
    </AbsoluteFill>
  );
};

export { E_OUT, Toggle };
