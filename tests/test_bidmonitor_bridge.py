"""Offline contract tests using a synthetic external CLI in a temporary venv."""
from __future__ import annotations

import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import venv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "tools"))
from acq_query import cli


def payload(status="complete"):
    url = "https://example.test/notice/P001"
    proof = {"value": "合成甲", "quote": "采购人：合成甲", "url": url, "status": "confirmed"}
    return {
        "schema_version": "clientreach.bidmonitor.v1", "query": {"keywords": ["软件"]},
        "status": status, "coverage": {"ccgp": {"status": status, "truncated": status != "complete"}},
        "metrics": {"requests": 2}, "errors": [] if status == "complete" else [{"code": "detail_budget"}],
        "results": [{"source": "ccgp", "url": url, "title": "软件采购招标公告",
                     "content": "软件采购招标公告\n采购人：合成甲\n采购需求：软件\n争议原文：甲、乙",
                     "field_evidence": {"buyer_name": [proof], "deadline": []},
                     "conflicts": {"project_number": [{"value": "P001", "quote": "P001"}]},
                     "published_at": None, "deadline": None, "buyer_name": "合成甲",
                     "winner_names": [], "candidate_names": [], "agency_name": None,
                     "project_number": None, "project_name": None, "budget": None, "lot": None,
                     "region": None, "stage": "tender", "role": "buyer", "evidence_status": "confirmed",
                     "event_id": "event", "version_id": "version", "change": "new",
                     "match_reasons": [{"term": "软件", "quote": "采购需求：软件", "url": url, "status": "confirmed"}],
                     "date_filter": {"status": "unconfirmed", "days": 30, "reason": "publication_unknown_or_disputed"},
                     "actionability": {"status": "unconfirmed", "reason": "stage_or_current_deadline_unconfirmed"},
                     "snapshot": "raw/synthetic.html", "future_extension": {"unmapped": "保留"}}],
        "future_extension": ["原样保留"],
    }


FAKE_MAIN = '''import json, os, sys, time
from pathlib import Path
control = json.loads(Path("control.json").read_text(encoding="utf-8"))
Path("capture.json").write_text(json.dumps({"argv": sys.argv[1:], "cwd": str(Path.cwd()),
    "utf8": os.environ.get("PYTHONUTF8"), "encoding": os.environ.get("PYTHONIOENCODING")}, ensure_ascii=False), encoding="utf-8")
time.sleep(control.get("sleep", 0))
print(control.get("stdout", json.dumps(control.get("payload"), ensure_ascii=False)))
print(control.get("stderr", "synthetic diagnostic"), file=sys.stderr)
sys.exit(control.get("exit", 0))
'''


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="clientreach-bridge-")
        cls.home = Path(cls.temp.name) / "工具 中文"
        cls.home.mkdir()
        venv.EnvBuilder(with_pip=False).create(cls.home / ".venv")
        package = cls.home / "clientreach_bidmonitor"
        package.mkdir()
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "__main__.py").write_text(FAKE_MAIN, encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.env = patch.dict(os.environ, {"CLIENTREACH_BIDMONITOR_HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.control(payload=payload())

    def bridge(self):
        spec = importlib.util.find_spec("acq_query.bidmonitor")
        self.assertIsNotNone(spec, "missing BidMonitor subprocess bridge")
        return importlib.import_module("acq_query.bidmonitor")

    def control(self, **kwargs):
        (self.home / "control.json").write_text(json.dumps(kwargs, ensure_ascii=False), encoding="utf-8")

    def capture(self):
        return json.loads((self.home / "capture.json").read_text(encoding="utf-8"))

    def test_chinese_metacharacters_are_one_literal_argument_and_utf8(self):
        bridge = self.bridge()
        term = '软件 "中文" & ; $(literal) ` > | %PATH%'
        company = '合成甲 "集团" & 乙'
        expected = payload()
        self.assertEqual(bridge.search(term, company=company, sources=["csg"], days=0,
                                       limit=3, max_requests=7, max_details=4, timeout=20), expected)
        captured = self.capture()
        argv = captured["argv"]
        self.assertEqual(argv[0], "search")
        self.assertEqual(argv[argv.index("--keyword") + 1], term)
        self.assertEqual(argv[argv.index("--company") + 1], company)
        self.assertEqual(argv[argv.index("--sources") + 1], "csg")
        for flag, value in (("--days", "0"), ("--limit", "3"), ("--max-requests", "7"), ("--max-details", "4")):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertIn("--include-existing", argv)
        self.assertLess(int(argv[argv.index("--max-seconds") + 1]), 20)
        self.assertEqual(Path(captured["cwd"]), self.home)
        self.assertEqual(captured["utf8"], "1")
        self.assertEqual(captured["encoding"], "utf-8")

    def test_explicit_keywords_replace_query_and_new_only_omits_flag(self):
        self.bridge().search("ignored", keywords=["软件", "人工智能"], include_existing=False)
        argv = self.capture()["argv"]
        self.assertEqual([argv[i + 1] for i, value in enumerate(argv) if value == "--keyword"], ["软件", "人工智能"])
        self.assertNotIn("--include-existing", argv)

    def test_company_only_is_allowed_but_empty_filters_are_rejected(self):
        bridge = self.bridge()
        bridge.search("", company="合成甲", keywords=[])
        self.assertNotIn("--keyword", self.capture()["argv"])
        for kwargs in ({}, {"keywords": []}, {"keywords": [" "]}):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(bridge.BidMonitorError, "filter"):
                bridge.search(" ", **kwargs)

    def test_input_types_source_keys_and_budgets_rejected_before_process(self):
        bridge = self.bridge()
        invalid = [{"sources": []}, {"sources": ["exa"]}, {"sources": "ccgp"}, {"sources": [1]},
                   {"keywords": "软件"}, {"keywords": [1]}, {"company": None},
                   {"days": -1}, {"limit": 1.5}, {"max_requests": True}, {"max_details": -1},
                   {"timeout": 0}, {"timeout": -1}, {"timeout": "180"}, {"include_existing": "yes"}]
        with patch.object(bridge.subprocess, "run", side_effect=AssertionError("must not invoke")):
            for kwargs in invalid:
                with self.subTest(kwargs=kwargs), self.assertRaises(bridge.BidMonitorError):
                    bridge.search("软件", **kwargs)
            with self.assertRaises(bridge.BidMonitorError):
                bridge.search(None)

    def test_missing_runtime_is_clear(self):
        bridge = self.bridge()
        with patch.dict(os.environ, {"CLIENTREACH_BIDMONITOR_HOME": str(self.home / "missing")}):
            with self.assertRaisesRegex(bridge.BidMonitorError, "runtime"):
                bridge.search("软件")

    def test_real_subprocess_timeout_is_clear_and_bounded(self):
        bridge = self.bridge()
        self.control(payload=payload(), sleep=3)
        with self.assertRaisesRegex(bridge.BidMonitorError, "timeout"):
            bridge.search("软件", timeout=1)

    def test_invalid_json_does_not_dump_unbounded_output(self):
        bridge = self.bridge()
        self.control(stdout="not-json" * 2000, stderr="diagnostic" * 2000)
        with self.assertRaisesRegex(bridge.BidMonitorError, "JSON") as caught:
            bridge.search("软件")
        self.assertLess(len(str(caught.exception)), 2500)

    def test_invalid_schema_containers_and_results_are_rejected(self):
        bridge = self.bridge()
        mutations = [("schema_version", "wrong"), ("status", "ok"), ("status", []), ("query", []),
                     ("coverage", []), ("metrics", []), ("results", {}), ("errors", {}),
                     ("results", ["bad"])]
        for field, value in mutations:
            bad = payload()
            bad[field] = value
            self.control(payload=bad)
            with self.subTest(field=field, value=value), self.assertRaisesRegex(bridge.BidMonitorError, "schema"):
                bridge.search("软件")
        for field, value in (("field_evidence", []), ("conflicts", []), ("content", None),
                             ("winner_names", "甲"), ("match_reasons", {}), ("date_filter", []),
                             ("actionability", []), ("published_at", 123)):
            bad = payload()
            bad["results"][0][field] = value
            self.control(payload=bad)
            with self.subTest(field=field), self.assertRaisesRegex(bridge.BidMonitorError, "schema"):
                bridge.search("软件")
        for field in ("query", "errors"):
            bad = payload()
            del bad[field]
            self.control(payload=bad)
            with self.subTest(missing=field), self.assertRaisesRegex(bridge.BidMonitorError, "schema"):
                bridge.search("软件")
        for field in ("event_id", "version_id", "change", "deadline", "role", "stage", "buyer_name"):
            bad = payload()
            del bad["results"][0][field]
            self.control(payload=bad)
            with self.subTest(missing_result=field), self.assertRaisesRegex(bridge.BidMonitorError, "schema"):
                bridge.search("软件")

    def test_nonzero_partial_and_blocked_preserve_raw_evidence_and_errors(self):
        bridge = self.bridge()
        for status, code in (("partial", 2), ("blocked", 3)):
            expected = payload(status)
            self.control(payload=expected, exit=code)
            with self.subTest(status=status):
                self.assertEqual(bridge.search("软件"), expected)

    def test_complete_json_with_failed_process_is_an_error(self):
        bridge = self.bridge()
        self.control(payload=payload(), exit=9)
        with self.assertRaisesRegex(bridge.BidMonitorError, "exit"):
            bridge.search("软件")

    def test_subprocess_uses_isolated_python_and_shell_false(self):
        bridge = self.bridge()
        real_run = subprocess.run
        with patch.object(bridge.subprocess, "run", wraps=real_run) as run:
            bridge.search("软件")
        args, kwargs = run.call_args
        self.assertEqual(Path(args[0][0]).parent.parent, self.home / ".venv")
        self.assertEqual(args[0][1:5], ["-X", "utf8", "-m", "clientreach_bidmonitor"])
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["encoding"], "utf-8")

    def call_cli(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr), \
             patch.object(cli, "load_settings", side_effect=AssertionError("legacy settings called")), \
             patch.object(cli.edge, "ensure_bridge", side_effect=AssertionError("Edge invoked")), \
             patch.object(cli.opencli, "run", side_effect=AssertionError("OpenCLI invoked")), \
             patch.object(cli.sources, "collect_profile", side_effect=AssertionError("legacy/Exa invoked")):
            code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_query_and_extra_keywords_or_new_only_and_no_legacy_calls(self):
        try:
            code, output, diagnostic = self.call_cli(["bidmonitor", "软件", "--keyword", "人工智能", "--company", "合成甲",
                                                     "--sources", "ccgp,csg", "--days", "7", "--limit", "2",
                                                     "--max-requests", "8", "--max-details", "3", "--timeout", "20", "--new-only"])
        except SystemExit as exc:
            self.fail(f"missing bidmonitor CLI branch (exit {exc.code})")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), payload())
        argv = self.capture()["argv"]
        self.assertEqual([argv[i + 1] for i, value in enumerate(argv) if value == "--keyword"], ["软件", "人工智能"])
        self.assertNotIn("--include-existing", argv)
        self.assertEqual(argv[argv.index("--sources") + 1], "ccgp,csg")
        self.assertNotIn("backend.app", sys.modules)

    def test_cli_partial_and_blocked_print_full_json_and_nonzero(self):
        self.bridge()
        for status, expected_code in (("partial", 2), ("blocked", 3)):
            expected = payload(status)
            self.control(payload=expected, exit=expected_code)
            code, output, _ = self.call_cli(["bidmonitor", "软件"])
            self.assertEqual(code, expected_code)
            self.assertEqual(json.loads(output), expected)

    def test_cli_bridge_failure_emits_schema_json_and_stderr(self):
        self.bridge()
        with patch.dict(os.environ, {"CLIENTREACH_BIDMONITOR_HOME": str(self.home / "missing")}):
            code, output, diagnostic = self.call_cli(["bidmonitor", "软件"])
        document = json.loads(output)
        self.assertNotEqual(code, 0)
        self.assertEqual(document["schema_version"], "clientreach.bidmonitor.v1")
        self.assertEqual(document["status"], "blocked")
        self.assertIsInstance(document["query"], dict)
        for name in ("coverage", "metrics"):
            self.assertIsInstance(document[name], dict)
        self.assertEqual(document["results"], [])
        self.assertTrue(document["errors"])
        self.assertIn("runtime", diagnostic)

    def test_cli_argument_errors_also_emit_schema_json(self):
        for argv in (["bidmonitor", "软件", "--timeout", "invalid"], ["bidmonitor"],
                     ["bidmonitor", "软件", "--unknown-option"]):
            try:
                code, output, diagnostic = self.call_cli(argv)
            except SystemExit as exc:
                self.fail(f"CLI argument error omitted JSON (exit {exc.code})")
            with self.subTest(argv=argv):
                self.assertNotEqual(code, 0)
                document = json.loads(output)
                self.assertEqual(document["schema_version"], "clientreach.bidmonitor.v1")
                self.assertEqual(document["status"], "blocked")
                self.assertEqual(document["results"], [])
                self.assertTrue(document["errors"])
                self.assertTrue(diagnostic)

    def test_old_company_parser_defaults_and_flags_unchanged(self):
        parser = cli.build_parser()
        defaults = vars(parser.parse_args(["company", "合成企业"]))
        self.assertEqual(defaults, dict(cmd="company", name="合成企业", days=None, limit=None, sources=None,
                                       no_profile=False, types=None, details=0, yes=False, no_login_prompt=False, json=False))
        args = parser.parse_args(["company", "合成企业", "--days", "180", "--sources", "yfbzb,ccgp", "--details", "3", "--yes"])
        self.assertEqual((args.days, args.sources, args.details, args.yes), (180, "yfbzb,ccgp", 3, True))

    @unittest.skipUnless(os.name == "nt", "PowerShell wrapper is Windows specific")
    def test_powershell_wrapper_bom_chinese_arguments_and_exit_code(self):
        wrapper = ROOT / "scripts" / "bidmonitor.ps1"
        self.assertTrue(wrapper.is_file(), "missing BidMonitor PowerShell wrapper")
        self.assertTrue(wrapper.read_bytes().startswith(b"\xef\xbb\xbf"))
        # Intercept only Python execution; invoke the real wrapper/acq.ps1 argument pipeline.
        harness = self.home / "wrapper-test.ps1"
        harness.write_text("function python { $global:LASTEXITCODE = 2; ConvertTo-Json -Compress -InputObject @($args) }\n"
                           "& '" + str(wrapper).replace("'", "''") + "' '软件 中文 & ;' --keyword '人工智能'\n"
                           "exit $LASTEXITCODE\n", encoding="utf-8-sig")
        completed = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
                                   capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)[-4:], ["bidmonitor", "软件 中文 & ;", "--keyword", "人工智能"])


if __name__ == "__main__":
    unittest.main()
