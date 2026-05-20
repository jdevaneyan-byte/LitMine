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


if __name__ == "__main__":
    unittest.main()
