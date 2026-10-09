"""Sprint 07 — Workspace API: a product workbench (BuildCostIQ) drives the kernel as people."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from sayelf_agent_ops.workspace import WorkspaceError, WorkspaceService
from sayelf_agent_ops.workspace_api import TokenStore, make_server

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "buildcostiq-project-department.json"
BOQ = "对比两版 BOQ 的清单特征变化和漏项"
DRAWING = "比较两版施工图的版本变化"
PROGRESS = "核对二标段本月形象进度是否滞后"
QUANTITY = "工程量复核"


def spec() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


class WorkspaceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.ws = WorkspaceService(spec=spec(), home=self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_w01_production_lead_is_a_member(self):
        members = {m["id"]: m for m in self.ws.project_view("human.pm")["members"]}
        self.assertEqual(["production-lead"], members["human.prod-lead"]["roles"])
        self.assertTrue(members["human.prod-lead"]["active"])

    def test_w02_progress_review_needs_production_lead_and_pm(self):
        wi = self.ws.submit("human.pm", PROGRESS)
        self.assertEqual("engineering.production", wi["role"])
        self.assertEqual("APPROVED", wi["state"])
        self.assertEqual({"production-lead", "project-manager"}, {r["role"] for r in wi["gate"]["roles"]})
        self.assertEqual([wi["id"]], [a["id"] for a in self.ws.my_approvals("human.prod-lead")])
        self.assertEqual([], self.ws.my_approvals("human.cost-lead"))
        self.ws.decide("human.prod-lead", wi["id"], True)
        done = self.ws.decide("human.pm", wi["id"], True)
        self.assertEqual("DELIVERED", done["state"])

    def test_w03_quantity_review_needs_production_lead_and_cost_lead(self):
        wi = self.ws.submit("human.pm", QUANTITY)
        self.assertEqual({"production-lead", "cost-lead"}, {r["role"] for r in wi["gate"]["roles"]})
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.decide("human.pm", wi["id"], True)
        self.assertEqual(403, ctx.exception.status)

    def test_w04_human_task_flow_through_the_workspace(self):
        wi = self.ws.submit("human.pm", DRAWING)
        self.assertEqual("human.tech-lead", wi["waiting_for"]["assignee"])
        self.assertEqual(1, len(self.ws.my_tasks("human.tech-lead")))
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.submit_task("human.prod-lead", wi["id"], "不是我的任务")
        self.assertEqual(403, ctx.exception.status)
        done = self.ws.submit_task("human.tech-lead", wi["id"], "B 版：3 号井位移 1.2 m")
        self.assertEqual("DELIVERED", done["state"])

    def test_w05_return_requires_a_reason(self):
        wi = self.ws.submit("human.pm", BOQ)
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.decide("human.cost-lead", wi["id"], False, "  ")
        self.assertEqual("REASON_REQUIRED_TO_RETURN", ctx.exception.code)
        back = self.ws.decide("human.cost-lead", wi["id"], False, "漏项口径不对")
        self.assertEqual("REWORK", back["state"])

    def test_w06_agents_and_strangers_have_no_access(self):
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.me("agent.engineering.commercial")
        self.assertEqual(403, ctx.exception.status)
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.me("human.nobody")
        self.assertEqual(401, ctx.exception.status)

    def test_w07_only_owner_manages_members_and_changes_persist(self):
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.add_member("human.cost-lead", {"id": "human.qa", "name": "质量负责人", "roles": ["qa-lead"]})
        self.assertEqual(403, ctx.exception.status)
        self.ws.add_member("human.pm", {"id": "human.qa", "name": "质量负责人", "roles": ["qa-lead"]})
        self.ws.remove_member("human.pm", "human.tech-lead")
        again = WorkspaceService(home=self.home)  # restart: project file wins over any spec
        members = {m["id"]: m for m in again.project_view("human.pm")["members"]}
        self.assertTrue(members["human.qa"]["active"])
        self.assertFalse(members["human.tech-lead"]["active"])
        with self.assertRaises(WorkspaceError):
            again.me("human.tech-lead")

    def test_w08_member_input_is_validated(self):
        for bad in ({"id": "agent.x", "roles": ["r"]}, {"id": "human.a b", "roles": ["r"]},
                    {"id": "human.ok", "roles": []}, {"id": "human.ok", "roles": ["bad role"]}):
            with self.assertRaises(WorkspaceError):
                self.ws.add_member("human.pm", bad)

    def test_w09_last_owner_cannot_leave(self):
        with self.assertRaises(WorkspaceError) as ctx:
            self.ws.remove_member("human.pm", "human.pm")
        self.assertEqual("LAST_OWNER", ctx.exception.code)


class WorkspaceHttpTests(unittest.TestCase):
    ORIGIN = "http://127.0.0.1:5173"

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        home = Path(cls.tmp.name)
        cls.ws = WorkspaceService(spec=spec(), home=home)
        cls.tokens = TokenStore(home)
        cls.tok = {m: cls.tokens.issue(m) for m in ("human.pm", "human.cost-lead", "human.prod-lead")}
        cls.server = make_server(cls.ws, cls.tokens, port=0, allowed_origins=(cls.ORIGIN,))
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, member=None, body=None, token=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if member or token:
            req.add_header("Authorization", f"Bearer {token or self.tok[member]}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, json.loads(resp.read()), resp.headers
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read()), err.headers

    def test_a01_health_needs_no_token_everything_else_does(self):
        self.assertEqual(200, self.call("GET", "/health")[0])
        status, body, _ = self.call("GET", "/me")
        self.assertEqual((401, "AUTH_REQUIRED"), (status, body["error"]))
        status, body, _ = self.call("GET", "/me", token="sao_forged")
        self.assertEqual((401, "INVALID_TOKEN"), (status, body["error"]))

    def test_a02_identity_comes_from_the_token_not_the_body(self):
        status, body, _ = self.call("GET", "/me", "human.prod-lead")
        self.assertEqual("human.prod-lead", body["member"]["id"])
        status, wi, _ = self.call("POST", "/workitems", "human.pm", {"text": BOQ, "actor": "human.cost-lead"})
        self.assertEqual(201, status)
        self.assertEqual("human.pm", wi["owner"])

    def test_a03_quorum_over_http(self):
        _, wi, _ = self.call("POST", "/workitems", "human.pm", {"text": PROGRESS})
        _, mine, _ = self.call("GET", "/approvals", "human.prod-lead")
        self.assertIn(wi["id"], [a["id"] for a in mine["approvals"]])
        self.call("POST", f"/workitems/{wi['id']}/decision", "human.prod-lead", {"approve": True})
        status, again, _ = self.call("POST", f"/workitems/{wi['id']}/decision", "human.prod-lead", {"approve": True})
        self.assertEqual(403, status)
        status, done, _ = self.call("POST", f"/workitems/{wi['id']}/decision", "human.pm", {"approve": True})
        self.assertEqual((200, "DELIVERED"), (status, done["state"]))

    def test_a04_approve_must_be_a_real_boolean(self):
        _, wi, _ = self.call("POST", "/workitems", "human.pm", {"text": BOQ})
        status, body, _ = self.call("POST", f"/workitems/{wi['id']}/decision", "human.cost-lead", {"approve": "yes"})
        self.assertEqual((400, "INVALID_INPUT"), (status, body["error"]))

    def test_a05_foreign_browser_origin_is_refused(self):
        status, body, _ = self.call("GET", "/me", "human.pm", headers={"Origin": "https://evil.example"})
        self.assertEqual((403, "ORIGIN_NOT_ALLOWED"), (status, body["error"]))
        status, _, headers = self.call("GET", "/me", "human.pm", headers={"Origin": self.ORIGIN})
        self.assertEqual(200, status)
        self.assertEqual(self.ORIGIN, headers["Access-Control-Allow-Origin"])

    def test_a06_body_must_be_json(self):
        req = urllib.request.Request(self.base + "/workitems", data=b"text=x", method="POST")
        req.add_header("Authorization", f"Bearer {self.tok['human.pm']}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(415, ctx.exception.code)

    def test_a07_unknown_paths_and_methods(self):
        self.assertEqual(404, self.call("GET", "/nope", "human.pm")[0])
        self.assertEqual(405, self.call("DELETE", "/workitems", "human.pm")[0])

    def test_a08_reissuing_a_token_revokes_the_old_one(self):
        old = self.tokens.issue("human.cost-lead")
        new = self.tokens.issue("human.cost-lead")
        self.assertEqual(401, self.call("GET", "/me", token=old)[0])
        self.assertEqual(200, self.call("GET", "/me", token=new)[0])
        type(self).tok["human.cost-lead"] = new

    def test_a09_tokens_are_stored_hashed(self):
        raw = (Path(self.tmp.name) / "workspace" / "tokens.json").read_text(encoding="utf-8")
        for token in self.tok.values():
            self.assertNotIn(token, raw)


if __name__ == "__main__":
    unittest.main()
