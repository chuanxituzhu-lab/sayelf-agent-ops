"""Sprint 08 — model port: Agent Ops runs skills on a model directly, no AI host platform."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from sayelf_agent_ops.providers.config import (ModelConfigError, ModelSetup, config_path, load_model,
                                               write_config)
from sayelf_agent_ops.workspace import WorkspaceService

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "buildcostiq-project-department.json"
BOQ = "对比两版 BOQ 的清单特征变化和漏项"


class FakeModel(BaseHTTPRequestHandler):
    """A local OpenAI-compatible endpoint. ``strict`` rejects response_format."""
    calls: list = []
    strict = False

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).calls.append(body)
        if type(self).strict and "response_format" in body:
            self.send_response(400); self.end_headers(); return
        payload = json.loads(body["messages"][1]["content"])
        answer = {"summary": f"{payload.get('skill', 'ping')} 草稿结论", "items": ["第 1 条", "第 2 条"],
                  "assumptions": ["假设两版编码一致"], "missing_inputs": ["B 版清单原件"], "ok": True}
        content = json.dumps(answer, ensure_ascii=False)
        if type(self).strict:
            content = "```json\n" + content + "\n```"
        data = json.dumps({"choices": [{"message": {"content": content}}],
                           "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ModelPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeModel)
        cls.endpoint = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeModel.calls, FakeModel.strict = [], False
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def workspace(self, model):
        return WorkspaceService(spec=json.loads(TEMPLATE.read_text(encoding="utf-8")), home=self.home, model=model)

    def test_m01_no_model_still_runs_with_honest_placeholders(self):
        setup = load_model(self.home, environ={})
        self.assertFalse(setup.describe()["configured"])
        wi = self.workspace(setup).submit("human.pm", BOQ)
        self.assertEqual("APPROVED", wi["state"])
        self.assertTrue(all(o["placeholder"] for o in wi["outputs"]))

    def test_m02_local_model_drafts_every_step_and_gates_still_apply(self):
        write_config(self.home, preset="ollama", endpoint=self.endpoint, model="qwen2.5:7b",
                     api_key_env=None, allow_remote=False)
        setup = load_model(self.home, environ={})
        self.assertFalse(setup.remote)
        wi = self.workspace(setup).submit("human.pm", BOQ)
        self.assertEqual(3, len(FakeModel.calls))  # one call per plan step
        self.assertEqual("APPROVED", wi["state"])  # cost-release quorum still required
        for out in wi["outputs"]:
            self.assertFalse(out["placeholder"])
            self.assertIn("未经计算或现场核实", out["note"])
            self.assertTrue(out["evidence"]["draft"])
            self.assertEqual(["B 版清单原件"], out["missing_inputs"])
        self.assertEqual("boq-diff", wi["outputs"][1]["type"])
        second_call = json.loads(FakeModel.calls[1]["messages"][1]["content"])
        self.assertEqual("boq-structure", second_call["earlier_steps"][0]["type"])  # step 2 sees step 1

    def test_m03_remote_model_without_consent_is_never_called(self):
        calls = []

        class Remote:
            model, endpoint = "remote-model", "https://example.invalid/v1"

            def complete_json(self, *a):
                calls.append(a)
                return {}

        setup = ModelSetup(Remote(), remote=True, consent=False, generic_skills=True, source="args")
        wi = self.workspace(setup).submit("human.pm", BOQ)
        self.assertEqual([], calls)
        self.assertNotEqual("APPROVED", wi["state"])
        failures = [e for e in wi["events"] if e["event"] == "executor-failed"]
        self.assertTrue(failures)
        self.assertIn("MODEL_CONSENT_REQUIRED", json.dumps(failures))

    def test_m04_service_without_json_mode_still_works(self):
        FakeModel.strict = True
        write_config(self.home, preset=None, endpoint=self.endpoint, model="m", api_key_env="",
                     allow_remote=False)
        reply = load_model(self.home, environ={}).provider.complete_json("x", {"skill": "ping"})
        self.assertEqual("ping 草稿结论", reply["summary"])
        self.assertEqual(2, len(FakeModel.calls))

    def test_m05_key_never_written_and_missing_key_is_named(self):
        write_config(self.home, preset="deepseek", endpoint=None, model=None, api_key_env=None, allow_remote=True)
        saved = config_path(self.home).read_text(encoding="utf-8")
        self.assertIn("DEEPSEEK_API_KEY", saved)
        self.assertNotIn("sk-", saved)
        with self.assertRaises(ModelConfigError) as ctx:
            load_model(self.home, environ={})
        self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))
        setup = load_model(self.home, environ={"DEEPSEEK_API_KEY": "sk-test"})
        self.assertTrue(setup.remote and setup.consent)
        self.assertNotIn("sk-test", json.dumps(setup.describe()))

    def test_m06_plain_http_to_a_remote_host_is_refused(self):
        with self.assertRaises(ModelConfigError):
            write_config(self.home, preset=None, endpoint="http://api.example.com/v1", model="m",
                         api_key_env="K", allow_remote=True)

    def test_m07_presets_need_a_model_name_where_none_is_default(self):
        with self.assertRaises(ModelConfigError):
            write_config(self.home, preset="doubao", endpoint=None, model=None, api_key_env=None, allow_remote=True)

    def test_m08_environment_overrides_the_file(self):
        write_config(self.home, preset="ollama", endpoint=self.endpoint, model="a", api_key_env=None,
                     allow_remote=False)
        setup = load_model(self.home, environ={"SAYELF_MODEL_ENDPOINT": self.endpoint, "SAYELF_MODEL_NAME": "b"})
        self.assertEqual(("env", "b"), (setup.source, setup.provider.model))

    def test_m09_capabilities_show_the_model_without_secrets(self):
        setup = load_model(self.home, environ={"SAYELF_MODEL_ENDPOINT": self.endpoint, "SAYELF_MODEL_NAME": "b",
                                               "SAYELF_MODEL_API_KEY": "sk-secret"})
        caps = self.workspace(setup).capabilities("human.pm")
        self.assertEqual("b", caps["model"]["model"])
        self.assertNotIn("sk-secret", json.dumps(caps))

    def test_m10_mcp_entry_starts_even_with_a_broken_model_config(self):
        from sayelf_agent_ops.service import AgentOpsService
        write_config(self.home, preset="deepseek", endpoint=None, model=None, api_key_env=None, allow_remote=True)
        env = {"SAYELF_AGENT_OPS_HOME": str(self.home)}
        with mock.patch.dict(os.environ, env, clear=False):
            for key in ("SAYELF_MODEL_ENDPOINT", "DEEPSEEK_API_KEY", "SAYELF_MODEL_API_KEY"):
                os.environ.pop(key, None)
            svc = AgentOpsService.from_env()
        self.assertIn("DEEPSEEK_API_KEY", svc.capabilities()["model_error"])


if __name__ == "__main__":
    unittest.main()
