"""QC：成片生成后的确定性检查，输出 qc_report.md。V0 不做视觉 AI 审片。"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import wave

from .assets import image_size
from .project import Project
from .storyboard import REAL_COMPONENTS
from .voice import SAMPLE_RATE, clip_path, read_pcm

log = logging.getLogger("trend_radar.video.qc")
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def ffprobe(path) -> dict:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True)
    return json.loads(p.stdout or "{}")


def detect(path, vf: str, pattern: str) -> list[tuple[float, ...]]:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf", vf, "-an", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [tuple(float(x) for x in m) for m in re.findall(pattern, p.stderr)]


def check_audio_sync(proj: Project, timings: dict, board: dict, captions: list[dict], fps: float) -> tuple[str, str]:
    """用实际配音采样独立检查每段起点，再检查渲染使用的分镜和字幕。"""
    scenes = timings["scenes"]
    layout = timings.get("clip_layout") or ("shots" if proj.exists("shots.json") else "scenes")
    try:
        track = read_pcm(proj.dir / "audio" / "voice.wav")
        if abs(len(track) / (2 * SAMPLE_RATE) - timings["duration"]) > 0.002:
            return FAIL, "配音采样长度与时间轴总时长不一致"
        for scene in scenes:
            sid = scene["scene_id"]
            clip = read_pcm(clip_path(proj, sid, layout))
            offset = round(scene["start"] * SAMPLE_RATE) * 2
            if track[offset:offset + len(clip)] != clip:
                return FAIL, f"第 {sid} 段的实际配音采样与标记起点 {scene['start']:.3f}s 不符"
    except (OSError, EOFError, ValueError, wave.Error) as e:
        return FAIL, f"无法核对配音采样：{e}"

    if [s["scene_id"] for s in scenes] != [s["scene_id"] for s in board["scenes"]]:
        return FAIL, "分镜与配音的场次不一致"
    scene_ids = {s["scene_id"] for s in scenes}
    if any(c["scene_id"] not in scene_ids for c in captions):
        return FAIL, "字幕引用了配音时间轴以外的场次"
    for scene, visual in zip(scenes, board["scenes"]):
        sid = scene["scene_id"]
        if not visual["shots"] or any(abs(start - scene["start"]) > 1 / max(fps, 1)
                                      for start in (visual["start"], visual["shots"][0]["start"])):
            return FAIL, f"第 {sid} 场的画面切点与配音起点不符"
        pages = [c for c in captions if c["scene_id"] == sid]
        tokens = [t for page in pages for t in page["tokens"]]
        words = scene["words"]
        if len(words) != len(tokens) or any(
                abs(tok["startMs"] - round(w["start"] * 1000)) > 2 or
                abs(tok["endMs"] - round(w["end"] * 1000)) > 2 for tok, w in zip(tokens, words)):
            return FAIL, f"第 {sid} 场的逐词字幕与配音标记不符"
        for index, page in enumerate(pages):
            group = page["tokens"]
            if not group:
                return FAIL, f"第 {sid} 场字幕缺少时间标记"
            # 分页字幕可在同一场内保持到下一页开始。
            next_start = pages[index + 1]["startMs"] if index + 1 < len(pages) else group[-1]["endMs"]
            if (abs(page["startMs"] - group[0]["startMs"]) > 2 or
                    not group[-1]["endMs"] - 2 <= page["endMs"] <= next_start + 2):
                return FAIL, f"第 {sid} 场字幕页显示时间与逐词标记不符"
    return PASS, f"{len(scenes)} 段配音采样与时间轴逐段匹配，场次切点及 {len(captions)} 页字幕通过核对"


def run_qc(proj: Project, cfg: dict) -> dict:
    vcfg = cfg.get("video", {})
    final = proj.dir / "render" / "final.mp4"
    if not final.exists():
        raise RuntimeError("还没有 render/final.mp4")
    board, captions = proj.read("storyboard.json"), proj.read("captions.json")
    script, pack, timings = proj.read("script.json"), proj.read("fact_pack.json", {}), proj.read("audio/timings.json")
    checks: list[tuple[str, str, str]] = []

    def add(name: str, status: str, detail: str):
        checks.append((name, status, detail))

    # ---- 成片本身 ----
    info = ffprobe(final)
    v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
    a = next((s for s in info.get("streams", []) if s["codec_type"] == "audio"), None)
    w, h = v.get("width"), v.get("height")
    dur = float(info.get("format", {}).get("duration", 0))
    fps = eval(v.get("r_frame_rate", "0/1").replace("/", " / ")) if v else 0  # noqa: S307  "30/1" 这样的分数
    add("画幅是 9:16", PASS if (w, h) == (vcfg.get("width", 1080), vcfg.get("height", 1920)) else FAIL, f"{w}×{h}")
    add("帧率", PASS if round(fps) == vcfg.get("fps", 30) else FAIL, f"{fps:.2f} fps")
    lo, hi = vcfg.get("min_seconds", 45), vcfg.get("max_seconds", 60)
    add("时长在 45–60 秒", PASS if lo <= dur <= hi else WARN, f"{dur:.1f} 秒")
    add("有音轨", PASS if a else FAIL, f"{a['codec_name']} {a.get('sample_rate')}Hz" if a else "没有音轨")
    add("画面与配音等长", PASS if abs(dur - timings["duration"]) < 0.3 else WARN,
        f"成片 {dur:.2f}s / 配音 {timings['duration']:.2f}s")

    black = detect(final, "blackdetect=d=0.3:pix_th=0.06", r"black_start:([\d.]+) black_end:([\d.]+)")
    add("没有黑帧", PASS if not black else FAIL,
        "无" if not black else "；".join(f"{s:.1f}–{e:.1f}s" for s, e in black))
    frozen = detect(final, "freezedetect=n=0.003:d=4", r"freeze_start: ([\d.]+)[\s\S]*?freeze_duration: ([\d.]+)")
    add("没有长时间静止的画面", PASS if not frozen else WARN,
        "无（没有超过 4 秒完全不动的画面）" if not frozen else "；".join(f"{s:.1f}s 起静止 {d:.1f}s" for s, d in frozen))

    # ---- 镜头节奏 ----
    shots = [sh for sc in board["scenes"] for sh in sc["shots"]]
    lengths = [sh["end"] - sh["start"] for sh in shots]
    long_shots = [(sh, n) for sh, n in zip(shots, lengths) if n > 6.5]
    add("没有明显过长的镜头", PASS if not long_shots else WARN,
        f"共 {len(shots)} 个镜头，平均 {sum(lengths) / len(lengths):.1f}s，最长 {max(lengths):.1f}s" +
        ("" if not long_shots else "；超过 6.5s：" + "、".join(f"{sh['start']:.1f}s 的 {sh['component']}" for sh, _ in long_shots)))
    gaps = [f"{a_['end']:.2f}→{b['start']:.2f}" for a_, b in zip(shots, shots[1:]) if b["start"] - a_["end"] > 0.05]
    add("没有空画面", PASS if not gaps and shots[0]["start"] < 0.05 else FAIL, "镜头首尾相接" if not gaps else "空档：" + "、".join(gaps))

    # 连续只有文字 / 图解的时间
    runs, cur = [], 0.0
    for sh, n in zip(shots, lengths):
        cur = cur + n if sh["component"] not in REAL_COMPONENTS else 0.0
        runs.append(cur)
    real_ratio = board["stats"]["real_ratio"]
    add("没有长时间只有文字", PASS if max(runs) <= 12 else WARN, f"连续非真实素材最长 {max(runs):.1f}s")
    add("真实素材占比", PASS if real_ratio >= 0.5 else WARN, f"{real_ratio * 100:.0f}%（目标 60–70%）")

    # ---- 素材 ----
    bad, stretched = [], []
    for sh in shots:
        if not sh.get("asset"):
            continue
        size = image_size(proj.dir / sh["asset"]["path"])
        if not size:
            bad.append(sh["asset"]["path"])
        elif size != (sh["asset"]["width"], sh["asset"]["height"]):
            stretched.append(sh["asset"]["path"])
    add("素材都能读取", PASS if not bad else FAIL, "全部可读" if not bad else "无法读取：" + "、".join(bad))
    add("素材没有被拉伸", PASS if not stretched else WARN,
        "模板按原始比例缩放或裁切，不拉伸" if not stretched else "记录的尺寸与文件不符：" + "、".join(stretched))
    lost = [n for n in board.get("notes", []) if "没找到" in n or "丢弃" in n or "兜底" in n]
    add("分镜要求都落实了", PASS if not lost else WARN, "全部落实" if not lost else "；".join(lost))

    # ---- 字幕 ----
    max_chars = vcfg.get("caption_max_chars", 13)
    over = [c["text"] for c in captions if len(c["text"]) > max_chars + 3]
    add("字幕不超屏", PASS if not over else WARN,
        f"{len(captions)} 页，最长 {max(len(c['text']) for c in captions)} 字" + ("" if not over else "；过长：" + " / ".join(over)))
    spoken = "".join(re.sub(r"[\W_]+", "", s["voice"]) for s in script["scenes"])
    shown = "".join(re.sub(r"[\W_]+", "", c["text"]) for c in captions)
    add("字幕和口播一致", PASS if spoken == shown else WARN,
        "字幕文字与口播逐字一致" if spoken == shown else f"口播 {len(spoken)} 字 / 字幕 {len(shown)} 字，存在差异")
    out_of_range = [c["text"] for c in captions if c["endMs"] / 1000 > dur + 0.2 or c["startMs"] >= c["endMs"]]
    if out_of_range:
        add("字幕和声音同步", FAIL, "字幕时间异常：" + " / ".join(out_of_range))
    else:
        add("字幕和声音同步", *check_audio_sync(proj, timings, board, captions, fps))

    # ---- 事实 ----
    fact_ids = {f["id"] for f in pack.get("verified_facts", [])}
    unsupported = [f"第 {s['scene_id']} 场" for s in script["scenes"] if s["claim_type"] == "FACT" and not s["fact_ids"]]
    unknown = [f"第 {s['scene_id']} 场" for s in script["scenes"] if any(i not in fact_ids for i in s["fact_ids"])]
    add("事实都有出处", PASS if not unsupported and not unknown else FAIL,
        f"{sum(1 for s in script['scenes'] if s['claim_type'] == 'FACT')} 场事实陈述都对应 Fact Pack 里的条目"
        if not unsupported and not unknown else "标为事实但没有出处：" + "、".join(unsupported + unknown))
    soft = [f"第 {s['scene_id']} 场（{s['claim_type']}）" for s in script["scenes"] if s["claim_type"] in ("INFERENCE", "PREDICTION")]
    add("推断和预测", PASS, ("这些场次是判断而非事实，成片里已用判断的语气表达：" + "、".join(soft)) if soft else "没有推断或预测")

    worst = FAIL if any(s == FAIL for _, s, _ in checks) else WARN if any(s == WARN for _, s, _ in checks) else PASS
    icon = {PASS: "✅", WARN: "⚠️", FAIL: "❌"}
    L = [f"# QC Report — {proj.id}", "", f"结论：**{worst}**（{sum(s == PASS for _, s, _ in checks)} 通过 / "
         f"{sum(s == WARN for _, s, _ in checks)} 提醒 / {sum(s == FAIL for _, s, _ in checks)} 失败）", "",
         "| 检查项 | 结果 | 说明 |", "|---|---|---|"]
    L += [f"| {n} | {icon[s]} {s} | {d} |" for n, s, d in checks]
    L += ["", "这些是可确定的自动检查。画面是否好看、节奏是否舒服、口播是否自然，需要人工观看判断。", ""]
    proj.path("qc_report.md").write_text("\n".join(L), encoding="utf-8")
    proj.write("qc.json", {"result": worst, "checks": [{"name": n, "status": s, "detail": d} for n, s, d in checks]})
    log.info("QC：%s", worst)
    if worst == FAIL:
        failed = "；".join(f"{name}：{detail}" for name, status, detail in checks if status == FAIL)
        raise RuntimeError(f"质检未通过：{failed}（见 qc_report.md）")
    return {"result": worst, "warnings": sum(s == WARN for _, s, _ in checks), "failures": sum(s == FAIL for _, s, _ in checks)}
