"""Backend smoke tests: pure helpers + API shape via TestClient.

These avoid asserting on specific DB contents (which vary) and instead check
structure, so they pass on any database state."""

from __future__ import annotations

import unittest


class NetworkHelperTests(unittest.TestCase):
    def test_split_authors(self):
        from backend.network import _split_authors

        names = _split_authors("Jane Doe, John Roe; Alice Lee and Bob Tan et al.")
        self.assertIn("Jane Doe", names)
        self.assertIn("Alice Lee", names)
        self.assertNotIn("et al.", names)
        self.assertEqual(_split_authors(""), [])
        self.assertEqual(_split_authors(None), [])

    def test_norm(self):
        from backend.network import _norm

        self.assertEqual(_norm("  a   b  "), "a b")
        self.assertEqual(_norm(None), "")


class ApiShapeTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        self.client = TestClient(app)

    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_projects_list_shape(self):
        r = self.client.get("/api/projects")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        if data:
            for key in ("id", "name", "library", "cited"):
                self.assertIn(key, data[0])

    def test_network_modes_return_nodes_edges(self):
        projects = self.client.get("/api/projects").json()
        if not projects:
            self.skipTest("no projects in database")
        pid = projects[0]["id"]
        for mode in ("citation", "author", "journal"):
            r = self.client.get(f"/api/projects/{pid}/network", params={"mode": mode})
            self.assertEqual(r.status_code, 200, mode)
            body = r.json()
            self.assertIn("nodes", body)
            self.assertIn("edges", body)
            self.assertEqual(body["mode"], mode)

    def test_network_rejects_bad_mode(self):
        projects = self.client.get("/api/projects").json()
        if not projects:
            self.skipTest("no projects in database")
        pid = projects[0]["id"]
        r = self.client.get(f"/api/projects/{pid}/network", params={"mode": "bogus"})
        self.assertEqual(r.status_code, 422)

    def test_search_splits_comma_queries(self):
        from backend.main import _split_queries
        self.assertEqual(_split_queries(["a, b", "c"]), ["a", "b", "c"])
        self.assertEqual(_split_queries(["  ", "x ,, y"]), ["x", "y"])

    def test_delete_project_removes_it(self):
        created = self.client.post(
            "/api/projects",
            json={"name": "Temp Del", "topic": "t", "type": "both"},
        ).json()
        pid = created["id"]
        r = self.client.delete(f"/api/projects/{pid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("deleted", body)
        self.assertIn("collected_articles", body["deleted"])
        self.assertEqual(self.client.get(f"/api/projects/{pid}").status_code, 404)

    def test_delete_missing_project_404(self):
        self.assertEqual(self.client.delete("/api/projects/99999999").status_code, 404)

    def test_rename_project(self):
        pid = self.client.post(
            "/api/projects", json={"name": "Before", "topic": "t", "type": "both"}
        ).json()["id"]
        try:
            r = self.client.patch(f"/api/projects/{pid}", json={"name": "After"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(self.client.get(f"/api/projects/{pid}").json()["name"], "After")
        finally:
            self.client.delete(f"/api/projects/{pid}")

    def test_duplicate_project_shell_only(self):
        pid = self.client.post(
            "/api/projects", json={"name": "Orig", "topic": "top", "type": "review"}
        ).json()["id"]
        dup_id = None
        try:
            r = self.client.post(f"/api/projects/{pid}/duplicate")
            self.assertEqual(r.status_code, 200)
            dup_id = r.json()["id"]
            dup = self.client.get(f"/api/projects/{dup_id}").json()
            self.assertTrue(dup["name"].startswith("Copy of"))
        finally:
            self.client.delete(f"/api/projects/{pid}")
            if dup_id:
                self.client.delete(f"/api/projects/{dup_id}")

    def test_keyword_suggest_shape(self):
        r = self.client.post("/api/keyword-suggest", json={"topic": "drug delivery", "seeds": []})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("terms", body)
        self.assertIsInstance(body["terms"], list)
        if not body["terms"]:
            self.assertTrue(body.get("unavailable"))


if __name__ == "__main__":
    unittest.main()
