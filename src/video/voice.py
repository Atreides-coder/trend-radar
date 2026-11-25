"""TTS + 字幕时间轴。

- TTSProvider 是统一接口；V0 只实现 EdgeTTSProvider（edge-tts：免费、不需要 key、带逐词时间戳）。
- 逐场合成，再拼成 audio/voice.wav：每一场的起止时间是精确的，以后重录某一场也不用全部重来。
- 字幕时间来自 TTS 返回的逐词边界，不按字符数猜。
- 时长不在 45–60 秒时，按实测语速让编剧改稿后重新合成。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import stat
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from .project import Project

log = logging.getLogger("trend_radar.video.voice")
PUNCT = "，。！？、；：,.!?;:…—"
QUOTES = "“”‘’\"'「」『』《》 "
SAMPLE_RATE = 48000


@dataclass
class Word:
    text: str
    start: float
    end: float


class TTSProvider:
    name = "base"

    def synthesize(self, text: str, out_path) -> list[Word]:
        """把 text 合成到 out_path（任意 ffmpeg 可读的格式），返回逐词时间（秒，相对这段音频开头）。"""
        raise NotImplementedError


class EdgeTTSProvider(TTSProvider):
    name = "edge-tts"

    def __init__(self, voice: str = "zh-CN-YunxiNeural", rate: str = "+0%", pitch: str = "+0Hz"):
        self.voice, self.rate, self.pitch = voice, rate, pitch

    def synthesize(self, text: str, out_path) -> list[Word]:
        import edge_tts

        async def go():
            comm = edge_tts.Communicate(text, self.voice, rate=self.rate, pitch=self.pitch, boundary="WordBoundary")
            words, audio = [], bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    audio.extend(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append(Word(chunk["text"], start, start + chunk["duration"] / 1e7))
            return words, bytes(audio)

        last = None
        for _ in range(3):  # 在线服务偶尔会断，重试几次
            try:
                words, audio = asyncio.run(go())
                if audio and words:
                    out_path.write_bytes(audio)
                    return words
                last = RuntimeError("TTS 没有返回音频或时间戳")
            except Exception as e:  # noqa: BLE001
                last = e
        raise RuntimeError(f"edge-tts 合成失败：{last}")


def make_provider(cfg: dict, rate: str | None = None) -> TTSProvider:
    tts = cfg.get("video", {}).get("tts", {})
    if tts.get("provider", "edge-tts") != "edge-tts":
        raise ValueError(f"未实现的 TTS provider：{tts.get('provider')}")
    return EdgeTTSProvider(voice=tts.get("voice", "zh-CN-YunxiNeural"), rate=rate or tts.get("rate", "+0%"),
                           pitch=tts.get("pitch", "+0Hz"))


def ffmpeg(*args: str):
    p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg 失败：{p.stderr.strip()[-400:]}")


def clip_path(proj: Project, scene_id: int, layout: str) -> Path:
    prefix = {"scenes": "scene", "shots": "shot"}[layout]
    return proj.dir / "audio" / layout / f"{prefix}_{scene_id:02d}.wav"


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (SAMPLE_RATE, 1, 2):
            raise ValueError(f"{path.name} 需要是 {SAMPLE_RATE} Hz、单声道、16 位 PCM")
        data = wav.readframes(wav.getnframes())
        if len(data) != wav.getnframes() * 2 or not data:
            raise ValueError(f"{path.name} 缺少 PCM 采样")
        return data


def assemble_voice(proj: Project, timings: dict) -> Path:
    """按时间轴的绝对采样位置写入各段，段间及末尾的空闲时间写成静音。"""
    scenes = timings["scenes"]
    if not scenes:
        raise ValueError("配音时间轴没有场次")
    layout = timings.get("clip_layout") or ("shots" if proj.exists("shots.json") else "scenes")
    track = bytearray(round(timings["duration"] * SAMPLE_RATE) * 2)
    end = 0
    for scene in scenes:
        pcm = read_pcm(clip_path(proj, scene["scene_id"], layout))
        start = round(scene["start"] * SAMPLE_RATE) * 2
        if start < end or start + len(pcm) > len(track):
            raise ValueError(f"第 {scene['scene_id']} 段音频与时间轴重叠或超出总时长")
        track[start:start + len(pcm)] = pcm
        end = start + len(pcm)

    out = proj.path("audio", "voice.wav")
    # 完整文件在同一目录就绪后再替换，缓存损坏时保留原配音。
    with tempfile.NamedTemporaryFile(dir=out.parent, suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        with wave.open(str(tmp_path), "wb") as wav:
            wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
            wav.writeframes(track)
        if out.exists():
            tmp_path.chmod(stat.S_IMODE(out.stat().st_mode))
        tmp_path.replace(out)
    finally:
        tmp_path.unlink(missing_ok=True)
    return out


def synthesize_all(proj: Project, provider: TTSProvider, scenes: list[dict], gap: float, tail: float,
                   *, layout: str = "scenes", ending: float = 0.4) -> dict:
    """从实际渲染的 WAV 帧数得到场次边界，配音、字幕和分镜共用这条时间轴。"""
    if not scenes or min(gap, tail, ending) < 0:
        raise ValueError("至少需要一段配音，停顿与收尾时长须大于或等于零")
    timeline, cursor = [], 0
    gap_frames = round(gap * SAMPLE_RATE)
    for s in scenes:
        wav = clip_path(proj, s["scene_id"], layout)
        wav.parent.mkdir(parents=True, exist_ok=True)
        words = []
        if s["voice"]:
            raw = wav.with_suffix(".mp3")
            words = provider.synthesize(s["voice"], raw)
            duration = words[-1].end + tail
            ffmpeg("-i", str(raw), "-af", "apad", "-t", f"{duration:.3f}", "-ar", str(SAMPLE_RATE),
                   "-ac", "1", "-c:a", "pcm_s16le", str(wav))
        elif layout == "shots":
            duration = s.get("silent_seconds", 2.0) - gap
            if duration <= 0:
                raise ValueError(f"静音镜头 {s['scene_id']} 的时长必须超过场间停顿")
            ffmpeg("-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{duration:.3f}", str(wav))
        else:
            raise ValueError(f"第 {s['scene_id']} 场没有口播")
        frames = len(read_pcm(wav)) // 2
        start = cursor / SAMPLE_RATE
        timeline.append({"scene_id": s["scene_id"], "start": start, "end": (cursor + frames) / SAMPLE_RATE,
                         "words": [{"text": w.text, "start": round(start + w.start, 3),
                                    "end": round(start + w.end, 3)} for w in words]})
        cursor += frames + gap_frames
    timings = {"provider": provider.name, "voice": getattr(provider, "voice", ""), "rate": getattr(provider, "rate", ""),
               "clip_layout": layout, "duration": (cursor - gap_frames + round(ending * SAMPLE_RATE)) / SAMPLE_RATE,
               "scenes": timeline}
    assemble_voice(proj, timings)
    return timings


def build_captions(scenes: list[dict], timings: dict, max_chars: int = 13) -> list[dict]:
    """把逐词时间轴切成短字幕页：先按标点分成小句，太长的小句再均匀拆成几页（不会剩下两三个字的尾巴）。
    每页带逐词时间（Remotion Caption 结构）。"""
    pages = []
    for scene, t in zip(scenes, timings["scenes"]):
        text, cursor = scene["voice"], 0
        clauses, clause = [], []
        for w in t["words"]:
            pos = text.find(w["text"], cursor)
            if pos >= 0:
                cursor = pos + len(w["text"])
            piece = dict(w)
            # 英文词之间保留空格，中文不加
            if clause and re.match(r"[A-Za-z0-9]", w["text"]) and re.search(r"[A-Za-z0-9]$", clause[-1]["text"]):
                piece["text"] = " " + w["text"]
            clause.append(piece)
            nxt = cursor
            while nxt < len(text) and text[nxt] in QUOTES:      # 跳过引号，看后面是不是标点
                nxt += 1
            if nxt < len(text) and text[nxt] in PUNCT:          # 这个词后面紧跟标点：一个小句结束
                clauses.append(clause)
                clause = []
        if clause:
            clauses.append(clause)

        for clause in clauses:
            total = sum(len(w["text"]) for w in clause)
            parts = max(1, -(-total // max_chars))               # 需要拆成几页
            target, groups, cur, used = total / parts, [], [], 0
            for w in clause:
                # 当前页已经够长，而且剩下的页数还没用完：换页
                if cur and len(groups) < parts - 1 and used + len(w["text"]) / 2 > target * (len(groups) + 1):
                    groups.append(cur)
                    cur = []
                cur.append(w)
                used += len(w["text"])
            groups.append(cur)
            for page in groups:
                page[0]["text"] = page[0]["text"].lstrip()
                line = "".join(w["text"] for w in page)
                pages.append({
                    "scene_id": scene["scene_id"], "text": line,
                    "startMs": round(page[0]["start"] * 1000), "endMs": round(page[-1]["end"] * 1000),
                    "tokens": [{"text": w["text"], "startMs": round(w["start"] * 1000), "endMs": round(w["end"] * 1000),
                                "timestampMs": round((w["start"] + w["end"]) * 500), "confidence": None} for w in page],
                    "emphasis": [e for e in scene.get("emphasis_words", []) if e in line],
                })
    # 每页一直显示到下一页开始（同一场内），避免字幕在词与词之间闪烁
    for a, b in zip(pages, pages[1:]):
        if a["scene_id"] == b["scene_id"]:
            a["endMs"] = b["startMs"]
    return pages


def run_voice(proj: Project, cfg: dict, runner_factory) -> dict:
    vcfg = cfg.get("video", {})
    lo, hi = vcfg.get("min_seconds", 45), vcfg.get("max_seconds", 60)
    target = vcfg.get("target_seconds", 52)
    gap, tail = vcfg.get("scene_gap_seconds", 0.12), vcfg.get("scene_tail_seconds", 0.18)
    rate = vcfg.get("tts", {}).get("rate", "+0%")
    script = proj.read("script.json")
    if not script:
        raise RuntimeError("还没有 script.json，请先运行 script")

    revisions = 0
    while True:
        provider = make_provider(cfg, rate)
        timings = synthesize_all(proj, provider, script["scenes"], gap, tail)
        dur = timings["duration"]
        chars = sum(len(s["voice"]) for s in script["scenes"])
        log.info("配音：%.1f 秒 / %d 字（%.2f 字/秒，rate %s）", dur, chars, chars / dur, rate)
        if lo <= dur <= hi or revisions >= vcfg.get("max_length_revisions", 2):
            break
        from .writer import revise_length
        script = revise_length(proj, runner_factory(), dur, round(target * chars / dur))
        revisions += 1

    proj.write("audio/timings.json", timings)
    captions = build_captions(script["scenes"], timings, vcfg.get("caption_max_chars", 13))
    proj.write("captions.json", captions)
    log.info("字幕：%d 页，最长 %d 字", len(captions), max(len(c["text"]) for c in captions))
    return {"duration": dur, "chars": chars, "voice": timings["voice"], "rate": rate, "captions": len(captions),
            "length_revisions": revisions, "in_range": lo <= dur <= hi}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="使用已有分段 WAV 离线校正配音，保留字幕和分镜时间")
    sub = parser.add_subparsers(dest="command", required=True)
    repair = sub.add_parser("repair-cached", help="按现有时间轴重拼 voice.wav，然后用原项目的渲染流程重出成片")
    repair.add_argument("project_id")
    project = Project(parser.parse_args().project_id)
    timings = project.read("audio/timings.json")
    if not timings:
        parser.error("没有已有的 audio/timings.json")
    print(assemble_voice(project, timings))
