"""
Phase 8 Step 1: Human Oversight Framework — Full Test Suite.

Covers:
  1. Autonomy Tiers (0-3) configuration and persistence.
  2. Interruption / Global Pause and Resume system.
  3. Action Permission Boundaries (allowed/blocked/default).
  4. Persistent Explainable Audit Logging.
  5. Rollback Framework (clipboard rollback, database record deletion rollback, manual rollback).
  6. Agentic Executor permission integration.
  7. Automation Governor integration.
  8. Quart API server endpoints.

Run::
    python -m unittest backend/tests/test_phase8_step1_oversight.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_TESTS_DIR)
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)

for p in (_BACKEND_DIR, _PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from database.db import get_connection
from human_oversight import human_oversight, HumanOversightManager
from agentic_executor import executor as agentic_executor
from automation_governor import automation_governor


class TestHumanOversight(unittest.TestCase):
    """Tests for backend/human_oversight.py."""

    def _clean_test_records(self):
        test_ids = ["test-act-123", "manual-act-1", "db-del-act-1", "clip-act-1", "api-rollback-1"]
        with get_connection() as conn:
            conn.execute("DELETE FROM human_oversight_settings WHERE key LIKE 'permission_boundary:%'")
            conn.execute("DELETE FROM notifications WHERE id = 'test-notif-999'")
            for tid in test_ids:
                conn.execute("DELETE FROM autonomy_audit_log WHERE action_id = ?", (tid,))
                conn.execute("DELETE FROM rollback_registry WHERE action_id = ?", (tid,))

    def setUp(self):
        # Save current settings to restore after test
        self.original_tier = human_oversight.get_autonomy_tier()
        self.original_paused = human_oversight.is_paused()
        self._clean_test_records()
        
    def tearDown(self):
        # Restore settings
        human_oversight.set_autonomy_tier(self.original_tier)
        if self.original_paused:
            human_oversight.pause_autonomy()
        else:
            human_oversight.resume_autonomy()
        self._clean_test_records()

    def test_tier_get_and_set(self):
        human_oversight.set_autonomy_tier(1)
        self.assertEqual(human_oversight.get_autonomy_tier(), 1)
        
        human_oversight.set_autonomy_tier(3)
        self.assertEqual(human_oversight.get_autonomy_tier(), 3)
        
        # Out-of-bounds capping
        human_oversight.set_autonomy_tier(-1)
        self.assertEqual(human_oversight.get_autonomy_tier(), 0)
        
        human_oversight.set_autonomy_tier(5)
        self.assertEqual(human_oversight.get_autonomy_tier(), 3)

    def test_pause_and_resume(self):
        human_oversight.resume_autonomy()
        self.assertFalse(human_oversight.is_paused())
        
        human_oversight.pause_autonomy()
        self.assertTrue(human_oversight.is_paused())
        
        human_oversight.resume_autonomy()
        self.assertFalse(human_oversight.is_paused())

    def test_action_permissions(self):
        # Default behavior
        self.assertEqual(human_oversight.get_action_permission("open_app"), "default")
        
        # Override allowed
        human_oversight.set_action_permission("open_app", "allowed")
        self.assertEqual(human_oversight.get_action_permission("open_app"), "allowed")
        
        # Override blocked
        human_oversight.set_action_permission("open_app", "blocked")
        self.assertEqual(human_oversight.get_action_permission("open_app"), "blocked")
        
        # Reset to default
        human_oversight.set_action_permission("open_app", "default")
        self.assertEqual(human_oversight.get_action_permission("open_app"), "default")

    def test_audit_logging(self):
        action_id = "test-act-123"
        human_oversight.log_action(
            action_id=action_id,
            action="notify",
            params={"message": "hello unit test"},
            attribution="test-suite",
            reasoning="Testing the audit logging capability",
            confidence=0.99,
            risk_level="safe",
            status="executed",
            detail="Sent successfully"
        )
        
        # Fetch audit log
        logs = human_oversight.get_audit_log(limit=100)
        match = [l for l in logs if l["action_id"] == action_id]
        
        self.assertEqual(len(match), 1)
        log = match[0]
        self.assertEqual(log["action"], "notify")
        self.assertEqual(log["params"]["message"], "hello unit test")
        self.assertEqual(log["attribution"], "test-suite")
        self.assertEqual(log["reasoning"], "Testing the audit logging capability")
        self.assertEqual(log["confidence"], 0.99)
        self.assertEqual(log["risk_level"], "safe")
        self.assertEqual(log["status"], "executed")
        self.assertEqual(log["detail"], "Sent successfully")

    def test_rollback_manual(self):
        action_id = "manual-act-1"
        human_oversight.log_action(
            action_id=action_id,
            action="open_app",
            params={"app": "notepad"},
            attribution="orchestrator",
            reasoning="Need editor",
            confidence=0.95,
            risk_level="moderate",
            status="executed",
            detail="Opened notepad"
        )
        
        human_oversight.register_rollback(
            action_id=action_id,
            undo_action="manual",
            undo_params={},
            description="Close notepad manually"
        )
        
        result = human_oversight.rollback(action_id)
        self.assertEqual(result["status"], "rolled_back")
        self.assertIn("manual verification", result["message"])

        # Check status updated in DB
        logs = human_oversight.get_audit_log(limit=100)
        match = [l for l in logs if l["action_id"] == action_id]
        self.assertEqual(match[0]["status"], "rolled_back")

    def test_rollback_delete_db_record(self):
        # Create a notification in database
        notif_id = "test-notif-999"
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO notifications (id, message, category, source, time, read) "
                "VALUES (?, 'Test Message', 'test', 'suite', ?, 0)",
                (notif_id, now)
            )
            
            # Verify it exists
            row = conn.execute("SELECT id FROM notifications WHERE id = ?", (notif_id,)).fetchone()
            self.assertIsNotNone(row)

        action_id = "db-del-act-1"
        human_oversight.log_action(
            action_id=action_id,
            action="notify",
            params={"message": "Test Message"},
            attribution="orchestrator",
            reasoning="Notify user",
            confidence=0.9,
            risk_level="safe",
            status="executed"
        )
        
        human_oversight.register_rollback(
            action_id=action_id,
            undo_action="delete_db_record",
            undo_params={"table": "notifications", "key_col": "id", "val": notif_id},
            description="Delete test notification"
        )
        
        result = human_oversight.rollback(action_id)
        self.assertEqual(result["status"], "rolled_back")
        
        # Verify notification is gone
        with get_connection() as conn:
            row = conn.execute("SELECT id FROM notifications WHERE id = ?", (notif_id,)).fetchone()
            self.assertIsNone(row)

    @patch("win32clipboard.OpenClipboard")
    @patch("win32clipboard.EmptyClipboard")
    @patch("win32clipboard.SetClipboardData")
    @patch("win32clipboard.CloseClipboard")
    def test_rollback_clipboard(self, mock_close, mock_set, mock_empty, mock_open):
        action_id = "clip-act-1"
        human_oversight.log_action(
            action_id=action_id,
            action="clipboard_store",
            params={"text": "new text"},
            attribution="orchestrator",
            reasoning="Copying notes",
            confidence=0.9,
            risk_level="safe",
            status="executed"
        )
        
        human_oversight.register_rollback(
            action_id=action_id,
            undo_action="clipboard_store",
            undo_params={"text": "previous text"},
            description="Restore clipboard text"
        )
        
        result = human_oversight.rollback(action_id)
        self.assertEqual(result["status"], "rolled_back")
        mock_open.assert_called_once()
        mock_empty.assert_called_once()
        mock_set.assert_called_once_with(13, "previous text")
        mock_close.assert_called_once()


class TestAgenticExecutorIntegration(unittest.TestCase):
    """Tests integration of AgenticExecutor with HumanOversight Framework."""

    def setUp(self):
        self.original_tier = human_oversight.get_autonomy_tier()
        self.original_paused = human_oversight.is_paused()
        human_oversight.resume_autonomy()
        
    def tearDown(self):
        human_oversight.set_autonomy_tier(self.original_tier)
        if self.original_paused:
            human_oversight.pause_autonomy()
        else:
            human_oversight.resume_autonomy()
            
        with get_connection() as conn:
            conn.execute("DELETE FROM human_oversight_settings WHERE key LIKE 'permission_boundary:%'")
            # Clean pending logs to avoid overflow in sequential runs
            conn.execute("DELETE FROM autonomy_audit_log WHERE status = 'pending'")

    def test_request_paused(self):
        human_oversight.pause_autonomy()
        result = agentic_executor.request("notify", {"message": "hello"}, "Test pause")
        self.assertEqual(result["status"], "rejected")
        self.assertIn("globally paused", result["reason"])

    def test_request_blocked(self):
        human_oversight.set_action_permission("notify", "blocked")
        result = agentic_executor.request("notify", {"message": "hello"}, "Test block override")
        self.assertEqual(result["status"], "rejected")
        self.assertIn("blocked by permission boundaries", result["reason"])

    def test_request_allowed_override(self):
        human_oversight.set_autonomy_tier(2) # Normal tier (requires confirmation for moderate)
        human_oversight.set_action_permission("open_url", "allowed")
        
        with patch.object(agentic_executor, "_do_open_url", return_value={"ok": True, "message": "success"}) as mock_url:
            result = agentic_executor.request("open_url", {"url": "https://example.com"}, "Test allowed override")
            self.assertEqual(result["status"], "executed")
            mock_url.assert_called_once()

    def test_request_tier0(self):
        human_oversight.set_autonomy_tier(0)
        result = agentic_executor.request("notify", {"message": "hello"}, "Test tier 0")
        self.assertEqual(result["status"], "rejected")
        self.assertIn("silent", result["reason"])

    def test_request_tier1_moderate(self):
        human_oversight.set_autonomy_tier(1) # notify only
        result = agentic_executor.request("open_url", {"url": "https://example.com"}, "Test tier 1 moderate")
        self.assertEqual(result["status"], "rejected")
        self.assertIn("Only notifications are allowed", result["reason"])

    def test_request_tier2_moderate(self):
        human_oversight.set_autonomy_tier(2) # confirmation for moderate
        result = agentic_executor.request("open_url", {"url": "https://example.com"}, "Test tier 2 moderate")
        self.assertEqual(result["status"], "pending")
        self.assertTrue(result["confirmation_needed"])

    def test_request_tier3_moderate(self):
        human_oversight.set_autonomy_tier(3) # full autonomy
        with patch.object(agentic_executor, "_do_open_url", return_value={"ok": True, "message": "success"}) as mock_url:
            result = agentic_executor.request("open_url", {"url": "https://example.com"}, "Test tier 3 moderate")
            self.assertEqual(result["status"], "executed")
            mock_url.assert_called_once()

    def test_request_safe_tier2(self):
        human_oversight.set_autonomy_tier(2)
        with patch.object(agentic_executor, "_do_notify", return_value={"ok": True, "message": "notified"}) as mock_notify:
            result = agentic_executor.request("notify", {"message": "test"}, "Test safe action")
            self.assertEqual(result["status"], "executed")
            mock_notify.assert_called_once()

    def test_approve_and_cancel_flow(self):
        human_oversight.set_autonomy_tier(2)
        # 1. Request moderate action -> goes to pending
        result = agentic_executor.request("open_url", {"url": "https://example.com"}, "Flow test")
        self.assertEqual(result["status"], "pending")
        action_id = result["action_id"]
        
        # 2. Check pending list
        pending_list = agentic_executor.get_pending()
        self.assertTrue(any(p["action_id"] == action_id for p in pending_list))
        
        # 3. Approve
        with patch.object(agentic_executor, "_do_open_url", return_value={"ok": True, "message": "success"}):
            approve_res = agentic_executor.approve(action_id)
            self.assertEqual(approve_res["status"], "executed")
            
        # 4. Request another and cancel
        result2 = agentic_executor.request("open_url", {"url": "https://google.com"}, "Flow test 2")
        action_id2 = result2["action_id"]
        
        cancel_res = agentic_executor.cancel(action_id2)
        self.assertEqual(cancel_res["status"], "cancelled")


class TestAutomationGovernorIntegration(unittest.TestCase):
    """Tests integration of AutomationGovernor with HumanOversight Framework."""

    def setUp(self):
        self.original_tier = human_oversight.get_autonomy_tier()
        self.original_paused = human_oversight.is_paused()
        human_oversight.resume_autonomy()

    def tearDown(self):
        human_oversight.set_autonomy_tier(self.original_tier)
        if self.original_paused:
            human_oversight.pause_autonomy()
        else:
            human_oversight.resume_autonomy()

    def test_governor_paused(self):
        human_oversight.pause_autonomy()
        allowed, reason = automation_governor.can_automate(
            source="productivity",
            action="notify",
            confidence=0.9,
            action_risk="safe"
        )
        self.assertFalse(allowed)
        self.assertIn("globally paused", reason)

    def test_governor_tier_lookup(self):
        human_oversight.set_autonomy_tier(0)
        allowed, reason = automation_governor.can_automate(
            source="productivity",
            action="notify",
            confidence=0.9,
            action_risk="safe"
        )
        self.assertFalse(allowed)
        self.assertIn("silenced", reason)

        human_oversight.set_autonomy_tier(1)
        # Tier 1 allows safe actions
        allowed, reason = automation_governor.can_automate(
            source="productivity",
            action="notify",
            confidence=0.9,
            action_risk="safe"
        )
        self.assertTrue(allowed)

        # Tier 1 blocks moderate actions
        allowed, reason = automation_governor.can_automate(
            source="productivity",
            action="open_url",
            confidence=0.9,
            action_risk="moderate"
        )
        self.assertFalse(allowed)
        self.assertIn("Only safe actions allowed", reason)


class TestAutonomyEndpoints(unittest.TestCase):
    """Verify Phase 8 Step 1 API endpoints in server.py."""

    @classmethod
    def setUpClass(cls):
        try:
            from server import app
            cls.app = app
            cls.has_app = True
        except Exception:
            cls.has_app = False

    def setUp(self):
        if not self.has_app:
            self.skipTest("Server not available")
        self.original_tier = human_oversight.get_autonomy_tier()
        self.original_paused = human_oversight.is_paused()
        human_oversight.resume_autonomy()

    def tearDown(self):
        human_oversight.set_autonomy_tier(self.original_tier)
        if self.original_paused:
            human_oversight.pause_autonomy()
        else:
            human_oversight.resume_autonomy()
        test_ids = ["api-rollback-1"]
        with get_connection() as conn:
            conn.execute("DELETE FROM human_oversight_settings WHERE key LIKE 'permission_boundary:%'")
            conn.execute("DELETE FROM autonomy_audit_log WHERE status = 'pending'")
            for tid in test_ids:
                conn.execute("DELETE FROM autonomy_audit_log WHERE action_id = ?", (tid,))
                conn.execute("DELETE FROM rollback_registry WHERE action_id = ?", (tid,))

    def run_async(self, coro):
        return asyncio.run(coro)

    def test_get_settings(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.get("/autonomy/settings")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertIn("autonomy_tier", data)
                self.assertIn("is_paused", data)
                self.assertIn("permissions", data)
        self.run_async(check())

    def test_post_tier(self):
        async def check():
            async with self.app.test_client() as client:
                # Valid
                resp = await client.post("/autonomy/tier", json={"tier": 3})
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertEqual(data["status"], "success")
                self.assertEqual(human_oversight.get_autonomy_tier(), 3)
                
                # Invalid (out of range)
                resp = await client.post("/autonomy/tier", json={"tier": 5})
                self.assertEqual(resp.status_code, 400)

                # Invalid (type)
                resp = await client.post("/autonomy/tier", json={"tier": "abc"})
                self.assertEqual(resp.status_code, 400)
        self.run_async(check())

    def test_pause_and_resume_endpoints(self):
        async def check():
            async with self.app.test_client() as client:
                # Pause
                resp = await client.post("/autonomy/pause")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertTrue(data["is_paused"])
                self.assertTrue(human_oversight.is_paused())

                # Resume
                resp = await client.post("/autonomy/resume")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertFalse(data["is_paused"])
                self.assertFalse(human_oversight.is_paused())
        self.run_async(check())

    def test_pending_approval_rejection_endpoints(self):
        async def check():
            async with self.app.test_client() as client:
                # Set tier to 2
                human_oversight.set_autonomy_tier(2)
                
                # Create a pending action via executor
                res = agentic_executor.request("open_url", {"url": "https://example.com"}, "api test")
                action_id = res["action_id"]

                # GET pending
                resp = await client.get("/autonomy/pending")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertTrue(any(p["action_id"] == action_id for p in data["pending"]))

                # POST approve
                with patch.object(agentic_executor, "_do_open_url", return_value={"ok": True, "message": "success"}):
                    resp_app = await client.post("/autonomy/approve", json={"action_id": action_id})
                    self.assertEqual(resp_app.status_code, 200)
                    data_app = await resp_app.get_json()
                    self.assertEqual(data_app["status"], "executed")

                # Create another pending action to reject
                res2 = agentic_executor.request("open_url", {"url": "https://google.com"}, "api test 2")
                action_id2 = res2["action_id"]

                # POST reject
                resp_rej = await client.post("/autonomy/reject", json={"action_id": action_id2})
                self.assertEqual(resp_rej.status_code, 200)
                data_rej = await resp_rej.get_json()
                self.assertEqual(data_rej["status"], "cancelled")
        self.run_async(check())

    def test_get_audit(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.get("/autonomy/audit?limit=5")
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertIn("audit_log", data)
                self.assertIsInstance(data["audit_log"], list)
        self.run_async(check())

    def test_post_rollback(self):
        async def check():
            action_id = "api-rollback-1"
            human_oversight.log_action(
                action_id=action_id,
                action="notify",
                params={},
                attribution="orchestrator",
                reasoning="test",
                confidence=0.9,
                risk_level="safe",
                status="executed"
            )
            human_oversight.register_rollback(
                action_id=action_id,
                undo_action="manual",
                undo_params={},
                description="manual action rollback description"
            )

            async with self.app.test_client() as client:
                resp = await client.post("/autonomy/rollback", json={"action_id": action_id})
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertEqual(data["status"], "rolled_back")
        self.run_async(check())

    def test_post_permission(self):
        async def check():
            async with self.app.test_client() as client:
                resp = await client.post("/autonomy/permission", json={"action": "open_app", "status": "blocked"})
                self.assertEqual(resp.status_code, 200)
                data = await resp.get_json()
                self.assertEqual(data["status"], "success")
                self.assertEqual(data["permission"], "blocked")
                self.assertEqual(human_oversight.get_action_permission("open_app"), "blocked")
                
                # Invalid status
                resp = await client.post("/autonomy/permission", json={"action": "open_app", "status": "invalid_status"})
                self.assertEqual(resp.status_code, 400)
        self.run_async(check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
