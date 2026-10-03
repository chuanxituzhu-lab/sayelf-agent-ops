import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from desktop.runtime import bootstrap


class DesktopWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Sayelf"
        bootstrap.initialize(self.root, "media")

    def add_request(self, workitem_id="WI-TEST-1", request="请为抖音做一期知识分享口播脚本"):
        folder = self.root / "workitems" / workitem_id
        folder.mkdir()
        path = folder / "request.json"
        path.write_text(json.dumps({
            "id": workitem_id,
            "request": request,
            "channel": "抖音",
            "attachments": [],
        }, ensure_ascii=False), encoding="utf-8")
        return path

    def test_registered_roles_are_idle_until_explicitly_activated(self):
        state = bootstrap.health(self.root)
        self.assertEqual(0, state["active_roles"])
        self.assertTrue(all(not role["active"] for role in state["roles"]))

        updated = bootstrap.set_role_active(self.root, "media.content-planner", True)
        self.assertEqual(1, updated["active_roles"])
        self.assertTrue(next(role for role in updated["roles"] if role["id"] == "media.content-planner")["active"])
        self.assertEqual(1, bootstrap.health(self.root)["active_roles"])

    def test_inactive_role_blocks_then_activation_produces_local_workplan(self):
        request = self.add_request()
        blocked = bootstrap.create_workplan(self.root, request)
        self.assertEqual(11, blocked["code"])
        self.assertEqual("media.content-planner", blocked["data"]["required_role_id"])
        self.assertFalse((self.root / "outputs" / "WI-TEST-1.md").exists())

        bootstrap.set_role_active(self.root, "media.content-planner", True)
        planned = bootstrap.create_workplan(self.root, request)
        self.assertEqual(0, planned["code"])
        self.assertEqual("planned", planned["data"]["state"])
        self.assertEqual("video-script", planned["data"]["routing"]["deliverable_type"])
        self.assertIn("尚未执行", planned["data"]["result_content"])
        self.assertTrue((self.root / "workitems" / "WI-TEST-1" / "plan.json").is_file())
        self.assertTrue((self.root / "outputs" / "WI-TEST-1.md").is_file())

    def test_schema_one_migration_backups_and_preserves_existing_rows(self):
        root = Path(self.temporary.name) / "Legacy"
        root.mkdir()
        for name in bootstrap.DIRECTORIES:
            (root / name).mkdir()
        database = root / "runtime.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.executemany("INSERT INTO metadata VALUES (?, ?)", [
                ("app_id", bootstrap.APP_ID), ("schema", "1"),
                ("version", "0.1.0"), ("pack", "media"), ("mode", "personal"),
            ])
            connection.execute("CREATE TABLE saved_state (id TEXT PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO saved_state VALUES ('keep', 'existing')")
            connection.commit()
        finally:
            connection.close()

        state = bootstrap.initialize(root, "media")

        self.assertEqual(3, state["schema"])
        self.assertEqual(0, state["active_roles"])
        self.assertEqual(1, len(list((root / "backups").glob("runtime-schema-1-*.sqlite3"))))
        self.assertEqual(1, len(list((root / "backups").glob("runtime-schema-2-*.sqlite3"))))
        connection = sqlite3.connect(database)
        try:
            self.assertEqual(("existing",), connection.execute(
                "SELECT value FROM saved_state WHERE id='keep'"
            ).fetchone())
            self.assertEqual("3", connection.execute(
                "SELECT value FROM metadata WHERE key='schema'"
            ).fetchone()[0])
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
