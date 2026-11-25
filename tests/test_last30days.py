import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.video import last30days, research
from src.video.project import Project

LINK = "https://example.org/community"
STORY = {"source": "hackernews", "url": LINK, "title": "SQLite storage", "published_at": "2026-11-19",
         "engagement": {"points": 286, "comments": 72}}
REPORT = {"schema_version": "1.4", "source_status": {"github": "no-results", "hackernews": "ok"},
          "generated_at": "2026-11-25T00:00:00Z", "results": [STORY]}


class CommunityResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.install = Path(self.tmp.name) / "tool"
        cli = self.install / "skills/last30days/scripts/last30days.py"
        cli.parent.mkdir(parents=True)
        cli.touch()
        (self.install / "pyproject.toml").write_text('[project]\nversion = "4.6.0"')
        self.install_patch = patch.object(last30days, "INSTALL", self.install)
        self.install_patch.start()
        self.addCleanup(self.install_patch.stop)

    def test_public_title_only_and_isolated_cli(self):
        title = last30days.public_query("苹果更新 macOS", [{"title": "Apple updates macOS permissions"}])
        proc = subprocess.CompletedProcess([], 0, json.dumps(REPORT), "")
        with patch.dict("os.environ", {"OPENAI_API_KEY": "secret", "GH_TOKEN": "secret"}), \
                patch.object(subprocess, "run", return_value=proc) as call:
            result = last30days.collect(title, {"timeout_seconds": 22})
        args = call.call_args
        self.assertEqual(args.args[0][-2:], ["--", title])
        self.assertIn("--no-browser-cookies", args.args[0])
        self.assertIn("--research-only", args.args[0])
        self.assertIn("--search=hackernews,github", args.args[0])
        self.assertEqual(args.kwargs["env"]["PATH"], args.kwargs["cwd"])
        self.assertNotIn("OPENAI_API_KEY", args.kwargs["env"])
        self.assertNotIn("GH_TOKEN", args.kwargs["env"])
        self.assertEqual(args.kwargs["timeout"], 22)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["items"], [{"title": "SQLite storage", "url": LINK, "platform": "hackernews",
                                            "date": "2026-11-19", "engagement": {"points": 286, "comments": 72}}])

    def test_failures_and_empty_results_are_distinct(self):
        clean = {"schema_version": "1.4", "results": [], "source_status": dict.fromkeys(last30days.PLATFORMS, "no-results")}
        for report, expected in ((clean, "empty"), ({**clean, "source_status": {"github": "rate-limited"}}, "failed"),
                                 ({**clean, "schema_version": "2.0"}, "failed")):
            with self.subTest(expected=expected), patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(report), "")):
                self.assertEqual(last30days.collect("SQLite", {})["status"], expected)
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("last30days", 1)):
            self.assertEqual(last30days.collect("SQLite", {})["status"], "failed")
        with patch.object(last30days, "INSTALL", self.install / "missing"):
            self.assertEqual(last30days.collect("SQLite", {})["status"], "unavailable")
            self.assertEqual(last30days.collect("SQLite", {"enabled": False})["status"], "disabled")

    def test_comparison_and_invalid_links(self):
        bad = {**STORY, "url": "file:///private/file"}
        comparison = {"schema_version": "1.4", "comparison": True,
                      "reports": [{"report": REPORT}, {"report": {**REPORT, "results": [STORY, bad]}}]}
        items, _, degraded = last30days._read_export(comparison)
        self.assertEqual([item["url"] for item in items], [LINK])
        self.assertFalse(degraded)

    def test_discussion_excerpt_is_bounded_and_optional(self):
        rows = [{**STORY, "summary": "A community comment.\n" * 30},
                {**STORY, "url": LINK + "2", "summary": STORY["title"]}]
        items, _, _ = last30days._read_export({**REPORT, "results": rows})
        self.assertTrue(items[0]["summary"].startswith("A community comment. A community comment."))
        self.assertLessEqual(len(items[0]["summary"]), 350)
        self.assertTrue(items[0]["summary"].endswith("…"))
        self.assertNotIn("summary", items[1])

    def test_research_uses_leads_without_certifying_them(self):
        project_dir = Path(self.tmp.name) / "projects"
        with patch("src.video.project.PROJECTS_DIR", project_dir):
            proj = Project.create("test", event_id=None, title="SQLite", angle="private editorial direction",
                                  event={"canonical_title": "SQLite"})
        runner = Mock()
        runner.run.return_value = {
            "sources": [{"id": 1, "url": LINK, "type": "independent_media"},
                        {"id": 2, "url": "https://example.org/official", "type": "official"}],
            "verified_facts": [{"id": 1, "claim": "Unverified", "source_ids": [1]},
                               {"id": 2, "claim": "Verified", "source_ids": [1, 2]}],
            "inferences": [], "timeline": [{"source_ids": [1]}],
            "key_numbers": [{"source_ids": [2, 1]}], "predictions": []}
        leads = {"status": "ok", "message": "", "items": [{"url": LINK, "title": "Community report",
                                                             "summary": "A reader reports faster queries."}]}
        with patch.object(last30days, "collect", return_value=leads) as collect:
            research.run_research(proj, runner, {"video": {"last30days": {"timeout_seconds": 31}}})
        collect.assert_called_once_with("SQLite", {"timeout_seconds": 31})
        self.assertEqual(runner.run.call_args.kwargs["input_data"]["community_leads"], leads["items"])
        self.assertEqual(proj.read("research/last30days.json"), leads)
        pack = proj.read("fact_pack.json")
        self.assertEqual(pack["verified_facts"], [{"id": 2, "claim": "Verified", "source_ids": [2]}])
        self.assertEqual(pack["sources"][0]["type"], "community")
        self.assertEqual(pack["inferences"][0]["text"], "Unverified")
        self.assertEqual(pack["timeline"], [])
        self.assertEqual(pack["key_numbers"], [{"source_ids": [2]}])

    def test_missing_engine_preserves_standard_research(self):
        with patch("src.video.project.PROJECTS_DIR", Path(self.tmp.name) / "projects"):
            proj = Project.create("unused", event_id=None, title="SQLite", angle="", event={"canonical_title": "SQLite"})
        runner = Mock()
        runner.run.return_value = {"sources": [], "verified_facts": [], "inferences": [], "predictions": []}
        with patch.object(last30days, "INSTALL", self.install / "missing"):
            info = research.run_research(proj, runner)
        self.assertNotIn("community_leads", runner.run.call_args.kwargs["input_data"])
        self.assertTrue(proj.exists("fact_pack.json"))
        self.assertEqual(info["last30days_status"], "unavailable")

    def test_refresh_only_reads_title_and_replaces_complete_result(self):
        with patch("src.video.project.PROJECTS_DIR", Path(self.tmp.name) / "projects"):
            proj = Project.create("refresh", event_id=7, title="测试主题", angle="private angle", event={})
        previous = {"status": "empty", "items": [], "message": "旧结果"}
        proj.write("research/last30days.json", previous)
        fresh = {"status": "ok", "items": [STORY], "message": ""}
        with patch.object(research, "event_sources", return_value=[{"title": "SQLite"}]), \
                patch.object(research, "fetch_article_text", side_effect=AssertionError), \
                patch.object(last30days, "collect", return_value=fresh) as collect:
            with patch.object(Path, "replace", side_effect=OSError("test interrupted publish")):
                with self.assertRaises(OSError):
                    research.refresh_community_leads(proj, {})
            self.assertEqual(proj.read("research/last30days.json"), previous)
            self.assertEqual(research.refresh_community_leads(proj, {}), fresh)
            self.assertEqual(proj.read("research/last30days.json"), fresh)
            collect.assert_called_with("SQLite", {})
        self.assertFalse(list((proj.dir / "research").glob(".last30days-*")))

    def test_failed_refresh_labels_previous_items_and_research_uses_fresh_only(self):
        with patch("src.video.project.PROJECTS_DIR", Path(self.tmp.name) / "projects"):
            proj = Project.create("cached", event_id=None, title="SQLite", angle="", event={})
        generated = REPORT["generated_at"]
        previous = {"status": "ok", "query": "SQLite", "items": [STORY], "generated_at": generated}
        proj.write("research/last30days.json", previous)
        runner = Mock()
        runner.run.return_value = {"sources": [], "verified_facts": [], "inferences": [], "predictions": []}
        failure = {"status": "failed", "query": "SQLite", "items": [], "message": "timeout"}
        with patch.object(last30days, "collect", side_effect=lambda *args: dict(failure)):
            info = research.run_research(proj, runner)
            saved = proj.read("research/last30days.json")
            self.assertEqual(saved["status"], "failed")
            self.assertTrue(saved["from_cache"])
            self.assertEqual(saved["items"], [STORY])
            self.assertEqual(saved["last_success_at"], generated)
            self.assertIn("attempted_at", saved)
            self.assertNotIn("community_leads", runner.run.call_args.kwargs["input_data"])
            self.assertEqual(info["community_leads"], 0)
            self.assertEqual(research.refresh_community_leads(proj, {})["last_success_at"], generated)
            proj.update(title="Another public topic")
            failure.update(query="Another public topic")
            fresh_failure = research.refresh_community_leads(proj, {})
            self.assertEqual(fresh_failure["items"], [])
            self.assertFalse(fresh_failure["from_cache"])
        proj.update(title="SQLite")
        proj.write("research/last30days.json", previous)
        with patch.object(last30days, "collect", return_value={"status": "empty", "query": "SQLite",
                                                               "items": [], "message": "no results"}):
            empty = research.refresh_community_leads(proj, {})
            self.assertFalse(empty["from_cache"])
            self.assertEqual(empty["items"], [])
