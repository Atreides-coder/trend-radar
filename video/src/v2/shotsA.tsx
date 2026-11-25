import { Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Easing, Img, staticFile } from "remotion";
import { Badge, Box, C, Cam, Cursor, E_IN, E_IO, FONT, FPS, H, Keyword, lerp, MONO, Plate, Toggle, useT, W } from "./kit";
import { Node, P, Path, Web } from "./map";
import { ShotProps } from "./types";

const dur = (s: ShotProps["s"]) => s.end - s.start;
/** 旁白里某个词开始的时间（相对镜头开头） */
export const wordAt = (s: ShotProps["s"], text: string, fallback: number) => {
  const w = s.words.find((x) => x.text.includes(text));
  return w ? w.start - s.start : fallback;
};

// 完全磁盘访问权限面板（986×1668）里“终端”那一行和它的开关
const ROW = { y: 334, top: 294, bottom: 374 };
const TOGGLE = { x: 855, y: 312, w: 70, h: 44 };

const DimOtherRows: React.FC<{ amount?: number }> = ({ amount = 0.62 }) => (
  <>
    <div style={{ position: "absolute", left: 0, top: 0, width: 986, height: ROW.top, background: `rgba(253,253,253,${amount})` }} />
    <div style={{ position: "absolute", left: 0, top: ROW.bottom, width: 986, height: 1668 - ROW.bottom, background: `rgba(253,253,253,${amount})` }} />
  </>
);

/** 01 · 极近特写：光标按下开关 */
export const S01: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const click = 0.45;
  const on = lerp(t, [click, click + 0.14], [0, 1]);
  const cx = lerp(t, [0, 0.38], [985, 893]), cy = lerp(t, [0, 0.38], [540, 342]);
  const ripple = lerp(t, [click, click + 0.5], [0, 1]);
  return (
    <AbsoluteFill style={{ background: C.ui }}>
      <Cam w={986} h={1668} ay={H * 0.42} easing={E_IO}
        keys={[{ t: 0, x: 780, y: 334, z: 2.6 }, { t: click, x: 795, y: 334, z: 2.8 }, { t: click + 0.16, x: 812, y: 334, z: 3.2 }, { t: dur(s), x: 815, y: 334, z: 3.3 }]}>
        <Plate src="assets/fda_pane.png" w={986} h={1668} />
        <DimOtherRows />
        <Toggle {...TOGGLE} on={on} />
        {t >= click && (
          <div style={{ position: "absolute", left: 890 - 60 * ripple, top: 334 - 60 * ripple, width: 120 * ripple, height: 120 * ripple,
            borderRadius: "50%", border: `3px solid ${C.green}`, opacity: 1 - ripple }} />
        )}
        <Cursor x={cx} y={cy} scale={0.5} pressed={t > click - 0.04 && t < click + 0.12} />
      </Cam>
      <Keyword text="1 次" at={click + 0.05} x={96} y={H * 0.42 - 74} size={128} color="#111" align="left" shadow={false} />
    </AbsoluteFill>
  );
};

const Doc: React.FC<{ title: string; text: string; from: number; speed?: number }> = ({ title, text, from, speed = 420 }) => {
  const t = useT();
  const shown = text.slice(0, Math.max(0, 150 + Math.floor((t - from) * speed)));
  return (
    <div style={{ position: "absolute", left: 70, top: 300, width: 940, height: 1060, borderRadius: 28, background: "#fbfbf9", overflow: "hidden",
      boxShadow: "0 40px 100px rgba(0,0,0,0.6)", scale: `${lerp(t, [from, from + 0.18], [1.07, 1])}` }}>
      <div style={{ height: 76, background: "#e9e9e6", display: "flex", alignItems: "center", gap: 12, padding: "0 26px" }}>
        {["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 20, height: 20, borderRadius: 10, background: c }} />)}
        <div style={{ flex: 1, textAlign: "center", marginRight: 84, fontSize: 30, color: "#555", fontWeight: 600 }}>{title}</div>
      </div>
      <div style={{ padding: "30px 40px", fontSize: 35, lineHeight: 1.6, color: "#1c1c1c", whiteSpace: "pre-wrap" }}>
        {shown}<span style={{ background: C.amber, color: C.amber }}>|</span>
      </div>
    </div>
  );
};

const TermStill: React.FC<{ src: string; from: number; fx: number; fy: number; z: number; dim?: number }> = ({ src, from, fx, fy, z, dim = 0 }) => {
  const t = useT();
  const punch = lerp(t, [from, from + 0.2], [1.08, 1]);
  return (
    <div style={{ position: "absolute", inset: 0, scale: `${punch}` }}>
      <Cam w={740} h={756} ay={820} keys={[{ t: from, x: fx, y: fy, z: z * 0.94 }, { t: from + 0.6, x: fx, y: fy, z }]}>
        <Plate src={src} w={740} h={756} />
      </Cam>
      {dim > 0 && <AbsoluteFill style={{ background: `rgba(11,11,12,${dim})` }} />}
    </div>
  );
};

/** 02 · Agent 演示的快切：真实录屏 + 真实产出的文件 */
export const S02: React.FC<ShotProps> = ({ s, p }) => {
  const t = useT();
  const d = dur(s);
  const cut = [0, 0.32, 0.64, 1.0, 1.36, 1.72].map((x) => (x * d) / 2.3);
  const beat = cut.filter((c) => t >= c).length - 1;
  const step = Math.min(p.demo.steps, beat);
  return (
    <AbsoluteFill style={{ background: C.term }}>
      {beat === 0 && <TermStill src="assets/agent_start.png" from={cut[0]} fx={330} fy={70} z={1.62} />}
      {beat === 1 && <TermStill src="assets/agent_step1.png" from={cut[1]} fx={360} fy={104} z={1.9} />}
      {beat === 2 && (
        <>
          <TermStill src="assets/agent_step1.png" from={cut[2]} fx={360} fy={104} z={1.9} dim={0.78} />
          {p.demo.files.map((f, i) => (
            <div key={f} style={{ position: "absolute", left: 110 + (i % 2) * 60, top: 420 + i * 150, fontSize: 58, fontWeight: 700, color: C.text,
              padding: "20px 34px", borderRadius: 20, background: C.panel, border: `2px solid ${C.amber}`, fontFamily: FONT,
              opacity: lerp(t, [cut[2] + i * 0.045, cut[2] + i * 0.045 + 0.08], [0, 1]),
              translate: `${lerp(t, [cut[2] + i * 0.045, cut[2] + i * 0.045 + 0.2], [-80, 0])}px 0px` }}>
              <span style={{ color: C.amber, fontSize: 40, marginRight: 18 }}>读取</span>{f}
            </div>
          ))}
        </>
      )}
      {beat === 3 && <Doc title="邮件草稿.txt" text={p.demo.email} from={cut[3]} speed={520} />}
      {beat === 4 && <Doc title="待办.md" text={p.demo.todo} from={cut[4]} speed={520} />}
      {beat >= 5 && <TermStill src="assets/agent_done.png" from={cut[5]} fx={345} fy={150} z={1.72} />}
      <div style={{ position: "absolute", right: 56, top: 132, textAlign: "right", fontFamily: MONO }}>
        <div style={{ fontSize: 30, color: C.muted, letterSpacing: 2, fontFamily: FONT }}>它自己完成的步骤</div>
        <div style={{ fontSize: 150, fontWeight: 800, color: C.amber, lineHeight: 1 }}>{String(step).padStart(2, "0")}</div>
      </div>
      <Badge text="演示环境 · 示例数据" y={150} />
    </AbsoluteFill>
  );
};

/** 03 · 录屏坍缩成节点，连成一条路径 */
export const S03: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const k = lerp(t, [0, 0.8], [0, 1], E_IO);
  const z = 1.72 - 1.52 * k;
  const cx = 540 + (400 - 540) * k, cy = 760 + (1290 - 760) * k;
  const path = [P("finder"), P("terminal"), P("mail")];
  const prog = lerp(t, [0.85, 1.9], [0, 1], E_IO);
  const kw = wordAt(s, "下一步", 2.2);
  const flick = (phase: number) => (t > kw - 0.2 ? 0.25 + 0.75 * Math.abs(Math.sin((t - kw) * 7 + phase)) : 0);
  return (
    <AbsoluteFill style={{ background: C.space }}>
      {t < 1.0 && (
        <Img src={staticFile("assets/agent_done.png")} style={{ position: "absolute", width: 740 * z, height: 756 * z, left: cx - 370 * z, top: cy - 378 * z,
          borderRadius: 18 * k, opacity: lerp(t, [0.6, 0.95], [1, 0]) }} />
      )}
      <Path pts={[P("mail"), P("safari")]} progress={1} dashed head={false} width={6} opacity={flick(0)} />
      <Path pts={[P("mail"), P("messages")]} progress={1} dashed head={false} width={6} opacity={flick(1.6)} />
      <Path pts={path} progress={prog} />
      <Node id="terminal" at={0.55} />
      <Node id="finder" at={0.7} />
      <Node id="mail" at={0.9} ring={C.amber} ringAt={1.9} />
      <Node id="safari" at={1.5} opacity={0.4} />
      <Node id="messages" at={1.6} opacity={0.4} />
      <Keyword text="自己决定下一步" at={kw} y={1420} size={104} color={C.amber} />
      {t < 1.1 && <Badge text="演示环境 · 示例数据" />}
    </AbsoluteFill>
  );
};

/** 04 · 真实录屏：系统设置进入“完全磁盘访问权限” */
export const S04: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const sw = 1.45;                      // 面板切换发生在镜头的这个时刻（录屏里是 3.07 秒）
  const d = dur(s);
  return (
    <AbsoluteFill style={{ background: C.ui }}>
      <Cam w={986} h={1668} ay={H * 0.3}
        keys={[{ t: 0, x: 493, y: 860, z: 1.1 }, { t: 1.2, x: 493, y: 1032, z: 1.16 }, { t: sw + 0.1, x: 493, y: 1032, z: 1.16 },
          { t: sw + 0.9, x: 493, y: 330, z: 1.18 }, { t: d, x: 493, y: 320, z: 1.24 }]}>
        <Video src={staticFile("assets/settings_nav.mp4")} trimBefore={Math.round((3.07 - sw) * FPS)} muted style={{ position: "absolute", left: 0, top: 0, width: 986, height: 1668 }} />
        {t < sw && <Box x={14} y={996} w={958} h={72} at={0.4} pad={4} dim={false} />}
        {t > sw + 0.8 && <Box x={158} y={30} w={258} h={46} at={sw + 0.9} pad={8} dim={false} />}
        {t < sw + 0.25 && (
          <Cursor x={lerp(t, [0.1, 1.1], [880, 640])} y={lerp(t, [0.1, 1.1], [1260, 1040])} scale={0.72} pressed={t > sw - 0.12 && t < sw + 0.06} />
        )}
      </Cam>
    </AbsoluteFill>
  );
};

/** 05 · 真实录屏：终端被系统拒绝 */
export const S05: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const err = 1.55;                      // 报错出现的时刻（录屏从 3.0 秒开始播）
  return (
    <AbsoluteFill style={{ background: C.term }}>
      <Cam w={684} h={396} ay={760}
        keys={[{ t: 0, x: 342, y: 170, z: 1.5 }, { t: err, x: 342, y: 150, z: 1.58 }, { t: err + 0.35, x: 342, y: 80, z: 1.58 }, { t: dur(s), x: 342, y: 76, z: 1.62 }]}>
        <Video src={staticFile("assets/terminal_denied.mp4")} trimBefore={Math.round(3.0 * FPS)} muted style={{ position: "absolute", left: 0, top: 0, width: 684, height: 396 }} />
        <Box x={326} y={48} w={326} h={28} at={err + 0.12} pad={5} color={C.red} />
      </Cam>
      <Keyword text="没有权限" at={err + 0.3} y={1040} size={150} color={C.red} />
      <div style={{ position: "absolute", left: 0, width: W, top: 1230, textAlign: "center", fontSize: 40, color: C.muted, fontFamily: MONO,
        opacity: lerp(t, [err + 0.45, err + 0.7], [0, 1]) }}>Operation not permitted</div>
    </AbsoluteFill>
  );
};

/** 06 · 报错后面是什么：三个真实应用 */
export const S06: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const tilt = lerp(t, [0, 0.5], [0, 1], E_IO);
  const items = [
    { icon: "assets/icon_mail.png", zh: "邮件", path: "~/Library/Mail", at: wordAt(s, "邮件", 0.1) },
    { icon: "assets/icon_messages.png", zh: "聊天记录", path: "~/Library/Messages", at: wordAt(s, "聊天", 0.8) },
    { icon: "assets/icon_safari.png", zh: "浏览记录", path: "~/Library/Safari", at: wordAt(s, "浏览", 1.7) },
  ];
  return (
    <AbsoluteFill style={{ background: `linear-gradient(180deg, ${C.term} 0%, ${C.space} 70%)` }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: W, height: 900, perspective: 1400 }}>
        <div style={{ position: "absolute", left: (W - 684 * 1.5) / 2, top: 250 - 60 * tilt, width: 684, height: 396, transformOrigin: "50% 100%",
          transform: `scale(${1.5 - 0.06 * tilt}) rotateX(${34 * tilt}deg)`, opacity: 1 - 0.2 * tilt, borderRadius: 14, overflow: "hidden" }}>
          <Video src={staticFile("assets/terminal_denied.mp4")} trimBefore={Math.round(6.0 * FPS)} playbackRate={1.8} muted style={{ width: 684, height: 396 }} />
        </div>
      </div>
      {items.map((it, i) => {
        const a = lerp(t, [it.at, it.at + 0.3], [0, 1]);
        return (
          <div key={it.zh} style={{ position: "absolute", left: 60 + i * 330, top: 960 - 90 * a, width: 300, textAlign: "center", opacity: a, scale: `${0.7 + 0.3 * a}` }}>
            <Img src={staticFile(it.icon)} style={{ width: 230, height: 230, filter: "drop-shadow(0 20px 40px rgba(0,0,0,0.7))" }} />
            <div style={{ fontSize: 58, fontWeight: 800, color: C.text, marginTop: 14 }}>{it.zh}</div>
            <div style={{ fontSize: 24, color: C.faint, fontFamily: MONO, marginTop: 8 }}>{it.path}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** 07 · 以前：备份软件只走一条线 */
export const S07: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const u = (t * 1.25) % 1;
  const shuttle = 1 - Math.abs(1 - 2 * u);
  const pts = [P("finder"), P("backup")];
  return (
    <AbsoluteFill style={{ background: C.space, scale: `${lerp(t, [0, dur(s)], [1, 1.03], Easing.linear)}` }}>
      {(["safari", "mail", "messages", "terminal"] as const).map((id) => <Node key={id} id={id} opacity={0.16} label={false} />)}
      <Path pts={pts} progress={1} color="#3a3a3d" head={false} width={8} />
      <Path pts={pts} progress={shuttle} color="#bdbcb5" width={8} />
      <Node id="finder" />
      <Node id="backup" />
      <div style={{ position: "absolute", left: 0, width: W, top: 330, textAlign: "center", fontSize: 44, color: C.muted, letterSpacing: 6 }}>备份软件</div>
      <Keyword text="只做一件事" at={wordAt(s, "只", 1.4)} y={1420} size={112} />
    </AbsoluteFill>
  );
};

/** 08 · 同一个开关，换了一个名字 */
export const S08: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const flip = Math.min(1.0, dur(s) * 0.55);
  const who = t < flip ? "备份软件" : "AI Agent";
  return (
    <AbsoluteFill style={{ background: C.ui }}>
      <Cam w={986} h={1668} ay={H * 0.42} keys={[{ t: 0, x: 815, y: 334, z: 3.3 }, { t: dur(s), x: 808, y: 334, z: 3.12 }]}>
        <Plate src="assets/fda_pane.png" w={986} h={1668} />
        <DimOtherRows />
        <Toggle {...TOGGLE} on={1} />
      </Cam>
      <div style={{ position: "absolute", left: 80, top: H * 0.42 - 250, fontSize: 84, fontWeight: 800, padding: "18px 40px", borderRadius: 24,
        background: t < flip ? "#111" : C.amber, color: t < flip ? "#fff" : "#111",
        scale: `${lerp(t, [flip, flip + 0.22], [1.18, 1])}`, transformOrigin: "0 50%" }}>{who}</div>
      <Keyword text="同一个开关" at={0.25} x={84} y={H * 0.42 + 140} size={104} color="#111" align="left" shadow={false} />
    </AbsoluteFill>
  );
};

/** 09 · 现在：Agent 停下来，自己选方向 */
export const S09: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const d = dur(s);
  const go = Math.max(1.5, d - 1.1);
  const prog = lerp(t, [go, d - 0.15], [0, 1], E_IO);
  const options = (["safari", "mail", "terminal", "messages"] as const);
  return (
    <AbsoluteFill style={{ background: C.space, scale: `${lerp(t, [0, d], [1, 1.05], Easing.linear)}` }}>
      {options.map((id, i) => (
        <Path key={id} pts={[P("finder"), P(id)]} progress={1} dashed head={false} width={6}
          opacity={t > 0.35 && t < go + 0.2 ? 0.2 + 0.8 * Math.abs(Math.sin(t * 6 + i * 1.3)) : 0} />
      ))}
      <Path pts={[P("finder"), P("safari")]} progress={prog} />
      {(["safari", "mail", "messages", "terminal"] as const).map((id) => <Node key={id} id={id} opacity={0.9} />)}
      <Node id="finder" ring={C.amber} ringAt={0.2} />
      <div style={{ position: "absolute", left: 0, width: W, top: 300, textAlign: "center", fontSize: 50, color: C.amber, letterSpacing: 6, fontWeight: 700 }}>AI Agent</div>
      <Keyword text="下一步？" at={0.7} out={go} y={1470} size={120} color={C.amber} />
    </AbsoluteFill>
  );
};

const Mini: React.FC<{ x: number; y: number; w: number; h: number; from: number; hold?: number; title: string; children: React.ReactNode }> = ({
  x, y, w, h, from, hold = 0.95, title, children,
}) => {
  const t = useT();
  if (t < from || t > from + hold + 0.2) return null;
  const a = lerp(t, [from, from + 0.18, from + hold, from + hold + 0.18], [0, 1, 1, 0], Easing.linear);
  return (
    <div style={{ position: "absolute", left: x, top: y, width: w, height: h, borderRadius: 22, overflow: "hidden", background: "#fbfbf9",
      border: `4px solid ${C.amber}`, boxShadow: "0 30px 70px rgba(0,0,0,0.7)", opacity: a, scale: `${0.82 + 0.18 * lerp(t, [from, from + 0.25], [0, 1])}` }}>
      <div style={{ height: 50, background: "#e7e7e3", fontSize: 24, color: "#555", display: "flex", alignItems: "center", padding: "0 18px", fontWeight: 600 }}>{title}</div>
      {children}
    </div>
  );
};

/** 10 · 路径上的每一站，都是它真的在做的事 */
export const S10: React.FC<ShotProps> = ({ s, p }) => {
  const t = useT();
  const w1 = wordAt(s, "翻", 0.1), w2 = wordAt(s, "开", 0.9), w3 = wordAt(s, "写", 2.0), w4 = wordAt(s, "敲", 2.9);
  return (
    <AbsoluteFill style={{ background: C.space }}>
      <Path pts={[P("finder"), P("safari")]} progress={1} head={t < w3 - 0.25} />
      <Path pts={[P("safari"), P("mail")]} progress={lerp(t, [w3 - 0.3, w3 + 0.15], [0, 1], E_IO)} head={t < w4 - 0.3} />
      <Path pts={[P("mail"), P("terminal")]} progress={lerp(t, [w4 - 0.35, w4 + 0.2], [0, 1], E_IO)} />
      <Node id="messages" opacity={0.9} />
      <Node id="finder" ring={t < w2 ? C.amber : undefined} ringAt={w1} />
      <Node id="safari" ring={t >= w2 && t < w3 ? C.amber : undefined} ringAt={w2} />
      <Node id="mail" ring={t >= w3 && t < w4 ? C.amber : undefined} ringAt={w3} />
      <Node id="terminal" ring={t >= w4 ? C.amber : undefined} ringAt={w4} />
      <Mini x={300} y={960} w={520} h={300} from={w1} hold={w2 - w1 - 0.1} title="演示文件夹">
        <div style={{ padding: "12px 22px", fontSize: 30, lineHeight: 1.55, color: "#222" }}>{p.demo.files.slice(0, 5).map((f) => <div key={f}>📄 {f}</div>)}</div>
      </Mini>
      <Mini x={130} y={740} w={600} h={330} from={w3} hold={w4 - w3 - 0.1} title="邮件草稿.txt">
        <div style={{ padding: "14px 22px", fontSize: 27, lineHeight: 1.5, color: "#222", whiteSpace: "pre-wrap" }}>
          {p.demo.email.slice(0, Math.max(0, Math.floor((t - w3) * 260)))}
        </div>
      </Mini>
      <Mini x={470} y={900} w={560} h={330} from={w4} hold={1.2} title="终端">
        <Video src={staticFile("assets/agent_demo.mp4")} trimBefore={Math.round(60.2 * FPS)} muted style={{ width: 760, marginLeft: -6, marginTop: -92 }} />
      </Mini>
      <Badge text="演示环境 · 示例数据" />
    </AbsoluteFill>
  );
};

const Half: React.FC<{ top: number; who: string; agent?: boolean; fill: number; show: number }> = ({ top, who, agent, fill, show }) => (
  <div style={{ position: "absolute", left: 0, top, width: W, height: 760, opacity: show }}>
    <div style={{ position: "absolute", left: 70, top: 20, fontSize: 40, color: agent ? C.amber : C.muted, fontWeight: 700, letterSpacing: 4 }}>{who}</div>
    <div style={{ position: "absolute", right: 70, top: 14, fontSize: 34, color: "#222", background: "#ececec", padding: "8px 20px", borderRadius: 12, fontWeight: 600 }}>完全磁盘访问权限</div>
    <div style={{ position: "absolute", left: W / 2 - 290, top: 110, width: 580, height: 580, borderRadius: "50%", border: `4px solid ${agent ? C.amber : "#77766f"}`, overflow: "hidden" }}>
      {agent && <div style={{ position: "absolute", left: 290 - 290 * fill, top: 290 - 290 * fill, width: 580 * fill, height: 580 * fill, borderRadius: "50%", background: "rgba(245,184,61,0.32)" }} />}
      <div style={{ position: "absolute", left: 290 - 540 * 0.6, top: 290 - 920 * 0.6, width: W, height: H, transform: "scale(0.6)", transformOrigin: "0 0" }}>
        {agent ? <Web progress={1} width={12} /> : <Path pts={[P("finder"), P("backup")]} progress={1} color="#bdbcb5" head={false} width={12} />}
        {(agent ? (["finder", "safari", "mail", "messages", "terminal"] as const) : (["finder", "backup"] as const)).map((id) => <Node key={id} id={id} label={false} size={170} />)}
      </div>
    </div>
  </div>
);

/** 11 · 同一个圈，里面能发生的事不一样多 */
export const S11: React.FC<ShotProps> = ({ s }) => {
  const t = useT();
  const k2 = wordAt(s, "全", dur(s) - 0.9);
  const fill = lerp(t, [wordAt(s, "引发", 1.4), k2 + 0.4], [0, 1], E_IN);
  return (
    <AbsoluteFill style={{ background: C.space }}>
      <Half top={130} who="备份软件" fill={0} show={lerp(t, [0, 0.3], [0, 1])} />
      <Half top={930} who="AI Agent" agent fill={fill} show={lerp(t, [0.25, 0.6], [0, 1])} />
      <Keyword text="同一个权限" at={0.3} out={k2 - 0.15} y={835} size={84} />
      <Keyword text="完全不同的风险" at={k2} y={830} size={92} color={C.amber} />
    </AbsoluteFill>
  );
};
