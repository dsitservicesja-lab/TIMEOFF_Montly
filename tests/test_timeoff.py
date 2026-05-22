import os
import tempfile
import unittest

from app import create_app


class TimeoffAppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path, "SECRET_KEY": "test"})
        self.client = self.app.test_client()

    def tearDown(self):
        self.tmpdir.cleanup()

    def login_as(self, username):
        return self.client.post("/login", data={"username": username}, follow_redirects=True)

    def test_monthly_limit_is_enforced(self):
        self.login_as("alice")
        self.client.post(
            "/request-timeoff",
            data={"request_date": "2026-05-10", "hours": "2", "reason": "Medical"},
            follow_redirects=True,
        )
        res = self.client.post(
            "/request-timeoff",
            data={"request_date": "2026-05-12", "hours": "3", "reason": "Family"},
            follow_redirects=True,
        )
        self.assertIn(b"Monthly limit exceeded", res.data)

    def test_supervisor_can_approve_branch_request(self):
        self.login_as("alice")
        self.client.post(
            "/request-timeoff",
            data={"request_date": "2026-06-01", "hours": "2", "reason": "Errand"},
            follow_redirects=True,
        )
        self.client.get("/logout", follow_redirects=True)
        self.login_as("sup_north")
        res = self.client.get("/dashboard")
        self.assertIn(b"Pending Branch Requests", res.data)
        self.client.post("/supervisor/decide/1", data={"decision": "approved"}, follow_redirects=True)
        self.client.get("/logout", follow_redirects=True)
        self.login_as("alice")
        updated = self.client.get("/dashboard")
        self.assertIn(b"approved", updated.data)


if __name__ == "__main__":
    unittest.main()
