"""在单独的 Python 进程调用 AutoClip v1.6 的本地镜头检测和编码器。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root, action, *args = sys.argv[1:]
    sys.path.insert(0, root)
    with tempfile.TemporaryDirectory(prefix="autoclip-media-") as data:
        os.environ["AUTOCLIP_DATA_DIR"] = data
        from backend import __version__
        if action == "detect":
            from backend.services.studio.framing import detect_cuts, split_shots
            video, length = Path(args[0]), float(args[1])
            # 上游的渐变检测一次解码一个场景；用重叠窗口限制长素材的内存占用。
            cuts = []
            start = 0.0
            while start < length:
                offset = max(0.0, start - 2)
                end = min(length, start + 120)
                cuts.extend(offset + cut for cut in detect_cuts(video, offset, end - offset)
                            if start <= offset + cut < end)
                start = end
            result = {"cuts": cuts, "shots": split_shots(length, cuts)}
        elif action == "encode":
            from backend.utils.ffmpeg_utils import get_ffmpeg_path
            from backend.utils.video_processor import VideoProcessor
            video, output, start, duration, mute = args
            cmd = VideoProcessor.build_extract_clip_command(
                get_ffmpeg_path(), Path(video), Path(output), start, float(duration))
            # 消除音轨与 B 帧引入的非零 MP4 起点，补齐奇数尺寸以兼容 yuv420p。
            cmd[1:1] = ["-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe"]
            filters = "fps=30:start_time=0,pad=ceil(iw/2)*2:ceil(ih/2)*2,tpad=stop_mode=clone:stop_duration=1"
            options = ["-vf", filters, "-bf", "0"]
            if mute == "1":
                options.append("-an")
            cmd[-1:-1] = options
            subprocess.run(cmd, check=True)
            result = {}
        else:
            raise ValueError(f"未知操作 {action}")
        print(json.dumps({"version": __version__, **result}))


if __name__ == "__main__":
    main()
