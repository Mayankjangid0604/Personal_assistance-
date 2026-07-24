"""
Server Compatibility Shim for Aisha AI Assistant (Phase 2 Step 6).

A standalone test harness that validates the full API contract after
the Flask → Quart migration.  Can be run independently to verify
every endpoint responds with the expected JSON schema.

Usage::

    python backend/server_compat.py

This does NOT start the server — it imports and uses Quart's test client.
"""

import asyncio
import json
import os
import sys

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
_DATABASE_DIR = os.path.join(_PROJECT_ROOT, "database")

for p in (_THIS_DIR, _DATABASE_DIR, _PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Contract definitions — every endpoint and its expected fields
# ---------------------------------------------------------------------------

API_CONTRACT = {
    # (method, path, body, expected_status, required_fields)
    "GET /health":              ("GET",  "/health",              None, 200, ["status", "assistant", "version", "timestamp"]),
    "GET /profile":             ("GET",  "/profile",             None, 200, ["profile"]),
    "GET /notifications":       ("GET",  "/notifications",       None, 200, ["notifications", "unread_count"]),
    "GET /dashboard":           ("GET",  "/dashboard",           None, 200, ["user_name", "goal", "emotion", "stats"]),
    "GET /reminders":           ("GET",  "/reminders",           None, 200, ["reminders"]),
    "GET /reminders/check":     ("GET",  "/reminders/check",     None, 200, ["triggered"]),
    "GET /habits":              ("GET",  "/habits",              None, 200, ["habits"]),
    "GET /learning":            ("GET",  "/learning",            None, 200, ["interests", "plans"]),
    "GET /journal":             ("GET",  "/journal",             None, 200, ["entries"]),
    "POST /chat":               ("POST", "/chat",                {"message": "hello"}, 200, ["response", "handler", "emotion", "session_id"]),
    "POST /chat (empty)":       ("POST", "/chat",                {"message": ""}, 400, ["error"]),
    "POST /chat (missing)":     ("POST", "/chat",                {}, 400, ["error"]),
    "POST /notifications/read": ("POST", "/notifications/read",  None, 200, ["marked"]),
    "POST /reset":              ("POST", "/reset",               None, 200, ["status"]),
}


async def validate_contract():
    """Run all contract checks and return (passed, failed, details)."""
    from server import app

    passed = 0
    failed = 0
    details = []

    async with app.test_client() as client:
        for label, (method, path, body, exp_status, exp_fields) in API_CONTRACT.items():
            try:
                if method == "GET":
                    resp = await client.get(path)
                else:
                    resp = await client.post(path, json=body)

                data = await resp.get_json()
                status_ok = resp.status_code == exp_status
                fields_ok = all(f in data for f in exp_fields) if data else False

                if status_ok and fields_ok:
                    passed += 1
                    details.append((label, "PASS", ""))
                else:
                    failed += 1
                    missing = [f for f in exp_fields if f not in (data or {})]
                    detail = ""
                    if not status_ok:
                        detail += f"status={resp.status_code} (expected {exp_status})"
                    if not fields_ok:
                        detail += f" missing={missing}"
                    details.append((label, "FAIL", detail))

            except Exception as e:
                failed += 1
                details.append((label, "ERROR", str(e)))

    return passed, failed, details


def main():
    print()
    print("=" * 70)
    print("  AISHA — Server API Contract Validation")
    print("=" * 70)
    print()

    passed, failed, details = asyncio.run(validate_contract())

    for label, status, detail in details:
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{status}]  {label}{suffix}")

    print()
    print("-" * 70)
    print(f"  Results: {passed} passed, {failed} failed, {passed + failed} total")

    if failed == 0:
        print("  ALL CONTRACTS VALID -- OK")
    else:
        print(f"  {failed} CONTRACTS BROKEN — review required")

    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
