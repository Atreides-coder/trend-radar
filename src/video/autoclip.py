"""导入 AutoClip 的本地导出，或用它的无模型镜头检测从长视频生成候选素材。"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .assets import update_library
from .project import ROOT, Project


@dataclass(frozen=True)
class Source:
    path: Path
    digest: str
    seconds: float


def _probe(video: Path) -> dict:
    if not video.is_file():
        raise ValueError(f"未找到视频：{video.name}")
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-format_whitelist", "mov,matroska,webm,avi,mpegts,mpeg,flv,asf,ogg",
            "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,duration:stream_disposition=attached_pic",
            "-of", "json", str(video)], capture_output=True, text=True, timeout=60)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        stream = next(s for s in streams if s.get("codec_type") == "video"
                      and not s.get("disposition", {}).get("attached_pic"))
        duration = stream.get("duration")
        if duration in (None, "", "N/A"):
            duration = data["format"]["duration"]
        duration = float(duration)
        if result.returncode or not (0 < duration < math.inf and stream["width"] > 0 and stream["height"] > 0):
            raise ValueError
    except (ValueError, KeyError, StopIteration, subprocess.TimeoutExpired) as e:
        raise ValueError(f"视频无法读取，或缺少有效时长和尺寸：{video.name}") from e
    return {"width": stream["width"], "height": stream["height"], "duration": duration,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams), "codec": stream["codec_name"]}


def _source(path: Path) -> Source:
    path = path.expanduser().resolve()
    seconds = _probe(path)["duration"]
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return Source(path, digest, seconds)


def _worker(action: str, *args) -> dict:
    upstream = Path(os.environ.get("AUTOCLIP_ROOT") or ROOT / ".tools" / "autoclip").expanduser().resolve()
    python = Path(os.environ.get("AUTOCLIP_PYTHON") or ROOT / ".tools" / "autoclip-env/bin/python").expanduser()
    if not (upstream / "backend/utils/video_processor.py").is_file() or not python.is_file():
        raise RuntimeError("找不到 AutoClip 源码或独立 Python，请先安装或设置 AUTOCLIP_ROOT 和 AUTOCLIP_PYTHON")
    proc = subprocess.run([str(python), "-I", "-B", str(Path(__file__).with_name("autoclip_worker.py")),
                           str(upstream), action, *map(str, args)], capture_output=True, text=True)
    if proc.returncode:
        detail = proc.stderr.strip().splitlines()
        raise RuntimeError("AutoClip 本地处理失败：" + "\n".join(detail[-4:]))
    return json.loads(proc.stdout)


def _matches(info: dict, duration: float, mute: bool) -> bool:
    return info["codec"] == "h264" and abs(info["duration"] - duration) <= 0.04 and (not mute or not info["has_audio"])


def _prepare(proj: Project, staging: Path, source: Source, *, start: float, duration: float | None, mute: bool, title: str | None,
            source_name: str, source_url: str, origin: dict) -> dict:
    if not math.isfinite(start) or start < 0 or start >= source.seconds:
        raise ValueError(f"开始时间必须在源视频时长 {source.seconds:.3f} 秒以内")
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ValueError("片段时长必须是正数")
    start_ms = round(start * 1000)
    end_ms = round(min(source.seconds, start + duration if duration is not None else source.seconds) * 1000)
    length = (end_ms - start_ms) / 1000
    if length <= 0:
        raise ValueError("裁切范围内没有视频")
    key = f"h264-30-v1/{source.digest}/{start_ms}/{end_ms}/{int(mute)}"
    asset_id = "autoclip_" + hashlib.sha256(key.encode()).hexdigest()[:24]
    out = proj.path("assets", asset_id + ".mp4")
    version = origin.get("version")
    info = None
    if out.exists():
        old = next((a for a in proj.read("assets/library.json", []) if a["id"] == asset_id), {})
        version = version or old.get("autoclip", {}).get("version")
        try:
            info = _probe(out)
        except ValueError:
            pass
    if info is None or not version or not _matches(info, length, mute):
        encoded = staging / out.name
        version = _worker("encode", source.path, encoded, f"{start_ms / 1000:.3f}", f"{length:.3f}", int(mute))["version"]
        info = _probe(encoded)
        if not _matches(info, length, mute):
            raise ValueError("编码输出的视频编码、时长或音轨未通过检查")
    metadata = {"version": version, "file": source_name, "source_sha256": source.digest,
                "start_seconds": start_ms / 1000, "end_seconds": end_ms / 1000, "muted": mute,
                **{key: value for key, value in origin.items() if value not in (None, "")}}
    asset = {"id": asset_id, "type": "autoclip_video", "media_type": "video", "path": f"assets/{out.name}",
             "width": info["width"], "height": info["height"], "duration": info["duration"],
             "source": source_name, "url": source_url, "description": title or source_name,
             "license_or_usage_note": "外部视频素材，沿用原片授权。", "autoclip": metadata}
    return asset


def _merge_source(old: dict, new: dict) -> dict:
    # 同一视频的正式导出保留项目号、片段号、标题等来源，即使后来只上传了同一文件。
    rank = {"file": 0, "detect_cuts": 1, "autoclip_export": 2}
    prior = old.get("autoclip", {})
    incoming = new["autoclip"]
    lesser, preferred = old, new
    if rank.get(prior.get("method"), 0) > rank.get(incoming.get("method"), 0):
        lesser, preferred = new, old
    origin = {**lesser.get("autoclip", {}), **{k: v for k, v in preferred["autoclip"].items() if v not in (None, "")}}
    description = preferred.get("description")
    if description == preferred.get("source") and lesser.get("description") != lesser.get("source"):
        description = lesser.get("description")
    return {**new, "autoclip": origin, "source": preferred.get("source") or lesser.get("source"),
            "description": description or lesser.get("description"),
            "url": new.get("url") or old.get("url", "")}


def _import_batch(proj: Project, requests: list[dict]) -> list[dict]:
    assets_dir = proj.path("assets", "library.json").parent
    with tempfile.TemporaryDirectory(prefix=".autoclip-", dir=assets_dir) as tmp:
        staging = Path(tmp)
        assets = [_prepare(proj, staging, **request) for request in requests]
        # 文件名由内容决定。所有编码和核查都通过后才提交，再一次性发布索引。
        for video in staging.glob("*.mp4"):
            os.replace(video, assets_dir / video.name)
        library = update_library(proj, assets, merge_entry=_merge_source)
    by_id = {asset["id"]: asset for asset in library}
    return [by_id[key] for key in dict.fromkeys(asset["id"] for asset in assets)]


def import_clip(proj: Project, video: Path, *, title: str | None = None, source_name: str | None = None,
                source_url: str = "", start: float = 0.0, duration: float | None = None, mute: bool = True) -> dict:
    request = dict(source=_source(Path(video)), start=start, duration=duration, mute=mute, title=title,
                   source_name=source_name or Path(video).name, source_url=source_url, origin={"method": "file"})
    return _import_batch(proj, [request])[0]


def scan(proj: Project, video: Path, *, max_clips: int = 6, clip_seconds: float = 6, mute: bool = True,
         source_url: str = "", source_name: str | None = None) -> dict:
    if max_clips < 1 or not math.isfinite(clip_seconds) or clip_seconds <= 0:
        raise ValueError("候选数量和片段时长必须大于零")
    source = _source(video)
    source_name = source_name or video.name
    detection = _worker("detect", source.path, source.seconds)
    shots = detection["shots"]
    # 镜头多时覆盖整个源片，每个候选均落在独立镜头内。
    indices = range(len(shots))
    if len(shots) > max_clips:
        if max_clips == 1:
            indices = [len(shots) // 2]
        else:
            indices = [round(i * (len(shots) - 1) / (max_clips - 1)) for i in range(max_clips)]
    requests = []
    for i in indices:
        left, right = shots[i]
        length = min(right - left, clip_seconds)
        start = left + (right - left - length) / 2
        requests.append(dict(source=source, start=start, duration=length, mute=mute,
                              title=f"{Path(source_name).stem} · 镜头 {i + 1}（{start:.1f}–{start + length:.1f} 秒）",
                              source_name=source_name, source_url=source_url,
                              origin={"method": "detect_cuts", "shot_start": left, "shot_end": right,
                                      "version": detection["version"]}))
    return {"detected_shots": len(shots), "detected_cuts": detection["cuts"], "assets": _import_batch(proj, requests)}


def import_manifest(proj: Project, manifest: Path, *, duration: float | None = None, mute: bool = True,
                    source_url: str = "") -> list[dict]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("需要 AutoClip 导出的 JSON 对象")
    if data.get("ok") and data.get("path"):
        pairs = [(data, data["path"])]
    else:
        fields = {"outputs": "video_path", "exports": "path", "clips": "file"}
        key = next((name for name in fields if name in data), None)
        if key is None or not isinstance(data[key], list):
            raise ValueError("JSON 中未找到 AutoClip 的 outputs、exports、clips 或单片导出记录")
        pairs = []
        for row in data[key]:
            if not isinstance(row, dict):
                raise ValueError("AutoClip 清单的视频记录格式错误")
            if key == "outputs" and row.get("status") != "completed" or key == "exports" and not row.get("ok"):
                continue
            pairs.append((row, row.get(fields[key])))
    requests = []
    for row, file in pairs:
        if not file:
            continue
        if not isinstance(file, str):
            raise ValueError("AutoClip 导出路径必须是本地文件名")
        source = _source(manifest.parent / file)
        title = row.get("title")
        for field in ("post", "result"):
            if not title and isinstance(row.get(field), dict):
                title = row[field].get("title")
        origin = {"method": "autoclip_export", "project_id": row.get("project_id") or data.get("project_id"),
                  "clip_id": row.get("clip_id") or row.get("id"), "strategy": row.get("preset") or row.get("strategy_id")}
        for name in ("start_time", "end_time", "score_100"):
            if row.get(name) is not None:
                origin[name] = row[name]
        requests.append(dict(source=source, start=0, duration=duration, mute=mute, title=title,
                             source_name=source.path.name, source_url=source_url, origin=origin))
    if not requests:
        raise ValueError("AutoClip 尚无可导入的已完成视频")
    return _import_batch(proj, requests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    single = sub.add_parser("import", help="导入已有视频，可指定起点和时长")
    single.add_argument("--start", type=float, default=0)
    single.add_argument("--title")
    multi = sub.add_parser("import-manifest", help="读取 AutoClip CLI/MCP 输出的 JSON")
    for command in (single, multi):
        command.add_argument("--duration", type=float, help="最多截取的秒数")
    detect = sub.add_parser("scan", help="用 AutoClip 检测镜头切换并截取候选视频")
    detect.add_argument("--max-clips", type=int, default=6)
    detect.add_argument("--clip-seconds", type=float, default=6)
    for command in (single, multi, detect):
        command.add_argument("project_id")
        command.add_argument("file", type=Path)
        command.add_argument("--source-url", default="")
        command.add_argument("--keep-audio", action="store_true", help="保留原片音轨，默认静音")
    args = parser.parse_args()
    proj = Project(args.project_id)
    if not re.fullmatch(r"[a-z0-9-]+", args.project_id) or not proj.state:
        parser.error("未找到目标视频项目")
    if proj.is_directed:
        parser.error("导演版使用 shots.json 与专属画面模板，请选择通用视频项目导入素材")
    options = {"mute": not args.keep_audio, "source_url": args.source_url}
    try:
        if args.action == "scan":
            result = scan(proj, args.file, max_clips=args.max_clips, clip_seconds=args.clip_seconds, **options)
        elif args.action == "import-manifest":
            result = import_manifest(proj, args.file, duration=args.duration, **options)
        else:
            result = import_clip(proj, args.file, start=args.start, duration=args.duration, title=args.title, **options)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"AutoClip：{error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
