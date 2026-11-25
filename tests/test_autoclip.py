import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from src.video import autoclip
from src.video.autoclip import _probe, import_clip, import_manifest, scan
from src.video.project import ROOT, Project


runtime = Path(os.environ.get("AUTOCLIP_PYTHON") or ROOT / ".tools/autoclip-env/bin/python")
checkout = Path(os.environ.get("AUTOCLIP_ROOT") or ROOT / ".tools/autoclip")


@unittest.skipUnless(runtime.is_file() and (checkout / "backend").is_dir() and shutil.which("ffmpeg"),
                     "需要已安装的 AutoClip 本地环境和 FFmpeg")
class AutoClipIntegrationTests(unittest.TestCase):
    def test_detect_import_retry_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp, patch("src.video.project.PROJECTS_DIR", Path(tmp)):
            root = Path(tmp)
            video = root / "recording.mp4"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=black:s=80x48:r=12:d=1[a];color=white:s=80x48:r=12:d=1[b];[a][b]concat=n=2:v=1:a=0",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac",
                "-pix_fmt", "yuv420p", "-shortest", str(video)], check=True)
            proj = Project.create("test", event_id=None, title="test", angle="", event={})
            original = {"id": "still", "type": "article_image", "path": "assets/still.jpg"}
            proj.write("assets/library.json", [original])
            detected = scan(proj, video, clip_seconds=0.5, source_name="原始录屏.mp4")
            self.assertEqual(detected["detected_shots"], 2)
            self.assertAlmostEqual(detected["detected_cuts"][0], 1.0, places=2)
            for item in detected["assets"]:
                info = _probe(proj.dir / item["path"])
                self.assertEqual(info["duration"], 0.5)
                self.assertFalse(info["has_audio"])
                self.assertEqual(item["source"], "原始录屏.mp4")
                self.assertEqual(item["autoclip"]["method"], "detect_cuts")

            audible = import_clip(proj, video, start=0.5, duration=0.5, mute=False)
            out = proj.dir / audible["path"]
            self.assertTrue(_probe(out)["has_audio"])
            mt = out.stat().st_mtime_ns
            again = import_clip(proj, video, start=0.5, duration=0.5, mute=False)
            self.assertEqual(again, audible)
            self.assertEqual(out.stat().st_mtime_ns, mt)
            self.assertIn(original, proj.read("assets/library.json"))

            variants = [
                {"outputs": [{"status": "failed"}, {"status": "completed", "id": "42", "video_path": video.name}]},
                {"exports": [{"ok": True, "clip_id": "42", "path": video.name}]},
                {"clips": [{"id": "42", "file": video.name, "score_100": 84}]},
                {"ok": True, "clip_id": "42", "path": video.name},
            ]
            for data in variants:
                manifest = root / "export.json"
                manifest.write_text(json.dumps({"project_id": "prior", **data}))
                assets = import_manifest(proj, manifest, duration=0.5)
                self.assertEqual(len(assets), 1)
                self.assertEqual(assets[0]["autoclip"]["clip_id"], "42")
                self.assertEqual(assets[0]["autoclip"]["project_id"], "prior")
            self.assertEqual(len(proj.read("assets/library.json")), 5)

            exported = import_manifest(proj, manifest, duration=0.5, source_url="https://example.org/source")[0]
            uploaded = import_clip(proj, video, duration=0.5, source_name="再次上传.mp4")
            self.assertEqual(uploaded, exported)
            self.assertEqual(uploaded["autoclip"]["method"], "autoclip_export")
            self.assertEqual(uploaded["autoclip"]["score_100"], 84)
            self.assertEqual(uploaded["url"], "https://example.org/source")

            before = proj.read("assets/library.json")
            before_files = sorted((proj.dir / "assets").glob("*.mp4"))
            bad = root / "broken.mp4"
            bad.write_text("损坏文件")
            manifest.write_text(json.dumps({"clips": [{"file": video.name}, {"file": bad.name}]}))
            with self.assertRaisesRegex(ValueError, "broken.mp4"):
                import_manifest(proj, manifest, duration=0.4)
            self.assertEqual(proj.read("assets/library.json"), before)
            self.assertEqual(sorted((proj.dir / "assets").glob("*.mp4")), before_files)

            # 已经完成第一个候选编码，第二个编码失败时，媒体和索引都不得发布。
            original_worker = autoclip._worker
            encodes = []
            def fail_second(action, *args):
                if action == "encode":
                    encodes.append(action)
                    if len(encodes) == 2:
                        raise RuntimeError("第二个编码失败")
                return original_worker(action, *args)
            with patch.object(autoclip, "_worker", side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "第二个编码失败"):
                    scan(proj, video, clip_seconds=0.4)
            self.assertEqual(len(encodes), 2)
            self.assertEqual(proj.read("assets/library.json"), before)
            self.assertEqual(sorted((proj.dir / "assets").glob("*.mp4")), before_files)
            self.assertFalse(list((proj.dir / "assets").glob(".autoclip-*")))
            with self.assertRaises(ValueError):
                import_clip(proj, video, start=40)
            with self.assertRaises(ValueError):
                import_clip(proj, manifest)
            self.assertEqual(proj.read("assets/library.json"), before)

            proj.write("shots.json", {"composition": "Custom"})
            stderr = io.StringIO()
            with patch.object(sys, "argv", ["autoclip", "import", proj.id, str(video)]), contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as stopped:
                    autoclip.main()
            self.assertEqual(stopped.exception.code, 2)
            self.assertIn("导演版使用 shots.json", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
