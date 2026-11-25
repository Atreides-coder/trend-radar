import json
import stat
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src.video.directed import synthesize
from src.video.project import Project
from src.video.qc import check_audio_sync
from src.video.voice import SAMPLE_RATE, Word, assemble_voice, build_captions, clip_path, read_pcm, synthesize_all


class ToneProvider:
    name = "tone"

    def synthesize(self, text, path):
        # WAV 输入同样可以交给 ffmpeg，测试可以完全离线。
        sample = int(text).to_bytes(2, "little")
        with wave.open(str(path), "wb") as wav:
            wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
            wav.writeframes(sample * (SAMPLE_RATE // 2))
        return [Word(text, 0.02, 0.3)]


class VoiceSyncTests(unittest.TestCase):
    def test_generic_and_directed_with_cached_repair(self):
        for layout, gap in (("scenes", 0.12), ("shots", 0.05)):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as tmp:
                with patch("src.video.project.PROJECTS_DIR", Path(tmp)):
                    project = Project("sample")
                scenes = [{"scene_id": 1, "voice": "1"}, {"scene_id": 2, "voice": "2"}]
                if layout == "shots":
                    shots = [{"id": s["scene_id"], "voice": s["voice"]} for s in scenes]
                    shots.insert(1, {"id": 3, "voice": "", "silent_seconds": 0.5})
                    spec = {"shots": shots}
                    project.write("shots.json", spec)
                    with patch("src.video.directed.EdgeTTSProvider", return_value=ToneProvider()):
                        timings = synthesize(project, spec, "")
                else:
                    timings = synthesize_all(project, ToneProvider(), scenes, gap, 0.18)
                timeline = timings["scenes"]
                if layout == "shots":
                    self.assertAlmostEqual(timeline[2]["start"] - timeline[1]["start"], 0.5)
                self.assertAlmostEqual(timeline[1]["start"] - timeline[0]["end"], gap)
                captions = build_captions(scenes, {"scenes": [s for s in timeline if s["words"]]})
                board = {"scenes": [{"scene_id": s["scene_id"], "start": s["start"], "shots": [{"start": s["start"]}]}
                                    for s in timeline]}
                args = (project, timings, board, captions, 30)
                self.assertEqual(check_audio_sync(*args)[0], "PASS")

                # 旧流程将间隙都堆到片尾。总时长相同，但第 2 段之后已错位。
                voice = project.path("audio", "voice.wav")
                reference = read_pcm(voice)
                packed = b"".join(read_pcm(clip_path(project, s["scene_id"], layout)) for s in timeline)
                with wave.open(str(voice), "wb") as wav:
                    wav.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                    wav.writeframes(packed.ljust(len(reference), b"\0"))
                self.assertEqual(check_audio_sync(*args)[0], "FAIL")
                # 旧版 time JSON 没有 clip_layout；使用其原始布局及既有字幕即可离线修复。
                legacy = json.loads(json.dumps(timings))
                del legacy["clip_layout"]
                voice.chmod(0o640)
                assemble_voice(project, legacy)
                self.assertEqual(stat.S_IMODE(voice.stat().st_mode), 0o640)
                self.assertEqual(read_pcm(voice), reference)
                self.assertEqual(check_audio_sync(project, legacy, board, captions, 30)[0], "PASS")
                captions[0]["startMs"] += 120
                self.assertEqual(check_audio_sync(*args)[0], "FAIL")


if __name__ == "__main__":
    unittest.main()
