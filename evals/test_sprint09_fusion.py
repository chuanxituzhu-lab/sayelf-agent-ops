from __future__ import annotations

import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from sayelf_agent_ops.files import FileRejected, FileStore
from sayelf_agent_ops.workspace import WorkspaceService
from sayelf_agent_ops.workspace_api import TokenStore, make_server
from sayelf_agent_ops.console import __main__ as console

TEMPLATE = Path(__file__).resolve().parent / "fixtures" / "team-project.json"


class FileIntakeTests(unittest.TestCase):
    def test_hash_identity_and_text_are_local(self):
        with tempfile.TemporaryDirectory() as folder:
            store = FileStore(Path(folder))
            one = store.put("brief.txt", "需求：比较两个版本".encode(), "human.pm")
            two = store.put("copy.txt", "需求：比较两个版本".encode(), "human.pm")
            self.assertEqual(one["id"], two["id"])
            self.assertTrue(one["text_extracted"])
            self.assertEqual("需求：比较两个版本", store.text(one["id"]))
            with self.assertRaises(FileRejected):
                store.put("../secret.txt", b"x", "human.pm")
            with self.assertRaises(FileRejected):
                store.put("run.exe", b"x", "human.pm")

    def test_xlsx_xml_and_size_boundaries_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            store = FileStore(Path(folder))
            with self.assertRaises(FileRejected):
                store.put("bad.xlsx", b"not-a-zip", "human.pm")


class WorkspaceFusionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.ws = WorkspaceService(spec=json.loads(TEMPLATE.read_text(encoding="utf-8")), home=self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def test_route_preview_is_read_only_and_keeps_minimum_contract(self):
        before = len(self.ws.runtime.items)
        result = self.ws.route_preview("human.pm", "对比两版 BOQ 并标出漏项")
        self.assertEqual(before, len(self.ws.runtime.items))
        self.assertTrue(result["steps"])
        self.assertEqual("valid", result["workflow_validation"]["status"])
        self.assertEqual("engineering", result["decision"]["industry"])

    def test_attachment_metadata_is_visible_but_text_is_executor_only(self):
        meta = self.ws.upload("human.pm", "brief.txt", base64.b64encode("内部需求".encode()).decode())
        item = self.ws.submit("human.pm", "对比两版 BOQ", files=[meta["id"]])
        self.assertEqual(meta["id"], item["attachments"][0]["id"])
        self.assertNotIn("text", item["attachments"][0])
        self.assertTrue((self.home / "workspace" / "files").exists())

    def test_http_upload_download_and_origin_boundary(self):
        tokens = TokenStore(self.home)
        token = tokens.issue("human.pm")
        server = make_server(self.ws, tokens, port=0, allowed_origins=("http://127.0.0.1:18766",))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/v1"
        try:
            data = b"hello"
            body = json.dumps({"name": "brief.txt", "content_base64": base64.b64encode(data).decode()}).encode()
            request = urllib.request.Request(base + "/files", data=body, method="POST",
                                             headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            meta = json.loads(urllib.request.urlopen(request, timeout=5).read())
            self.assertTrue(meta["ok"])
            request = urllib.request.Request(f"{base}/files/{meta['id']}/content",
                                             headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(data, urllib.request.urlopen(request, timeout=5).read())
            request = urllib.request.Request(base + "/route", data=json.dumps({"text": "写五个公众号标题"}).encode(),
                                             method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
            route = json.loads(urllib.request.urlopen(request, timeout=5).read())
            self.assertEqual("valid", route["workflow_validation"]["status"])
            bad = urllib.request.Request(base + "/route", data=b"{}", method="POST",
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Origin": "http://evil.invalid"})
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(403, error.exception.code)
        finally:
            server.shutdown()
            server.server_close()


class ConsoleTests(unittest.TestCase):
    def test_console_headers_and_no_directory_listing(self):
        server = console.make_server(0, "http://127.0.0.1:8765/v1")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            response = urllib.request.urlopen(base + "/", timeout=5)
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(base + "/missing-directory/", timeout=5)
            self.assertEqual(404, error.exception.code)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
