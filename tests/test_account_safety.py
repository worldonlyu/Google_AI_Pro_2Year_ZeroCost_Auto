"""Offline regression tests: fake records only, no app/engine import or browser.

The harness extracts the actual function bodies with AST. Dependencies are
whitelisted fakes; imports, credentials, browser launches and network access are
unavailable. These tests do not exercise subscription purchases or promotions.
"""
import ast
import asyncio
import builtins
import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(os.environ.get("GUARD_TEST_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from account_safety import account_run_lock_reason


class HttpError(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code


def forbidden(*args, **kwargs):
    raise AssertionError("Forbidden side effect/import/credential access in offline test")


class NoCredentials:
    get = forbidden
    __getitem__ = forbidden


def extract(relative, name, namespace, class_name=None):
    tree = ast.parse((ROOT / relative).read_text())
    scope = tree.body
    if class_name:
        scope = next(n for n in scope if isinstance(n, ast.ClassDef) and n.name == class_name).body
    node = copy.deepcopy(next(n for n in scope if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name))
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    # Postpone annotations; no dependency imports from production modules.
    import __future__
    exec(compile(module, str(ROOT / relative), "exec", flags=__future__.annotations.compiler_flag), namespace)
    return namespace[name]


def fake_account(account_id="fixture", **fields):
    return {"id": account_id, "status": "pending", "current_step": 0, **fields}


class LockPolicyTests(unittest.TestCase):
    def test_explicit_lock(self):
        self.assertIsNotNone(account_run_lock_reason(fake_account(automation_locked=True)))

    def test_completed_locked_without_flag(self):
        self.assertIsNotNone(account_run_lock_reason(fake_account(status="completed")))

    def test_pending_is_not_mislabeled_as_locked(self):
        self.assertIsNone(account_run_lock_reason(fake_account()))

    def test_resetting_status_does_not_clear_explicit_lock(self):
        account = fake_account(status="error", automation_locked=True)
        account["status"] = "pending"
        self.assertIsNotNone(account_run_lock_reason(account))


class RouteGuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = {"accounts": [fake_account(automation_locked=True)]}
        self.scheduled = []
        self.logs = []
        self.saves = []

        def save(cfg):
            self.config = copy.deepcopy(cfg)
            self.saves.append(copy.deepcopy(cfg))

        def schedule(coro):
            # Never execute a queued pipeline, even for the negative control.
            self.scheduled.append(coro.cr_code.co_name)
            coro.close()

        async def fake_worker(*args, **kwargs):
            forbidden()

        self.ns = {
            "__builtins__": {**vars(builtins), "__import__": forbidden},
            "account_run_lock_reason": account_run_lock_reason,
            "HTTPException": HttpError,
            "load_config": lambda: copy.deepcopy(self.config),
            "save_config": save,
            "ACTIVE_TASKS": {}, "BATCH_RUNNING": False, "STOP_BATCH": False,
            "asyncio": SimpleNamespace(create_task=schedule),
            "time": SimpleNamespace(strftime=lambda *a: "TEST", time=lambda: 0),
            "get_totp": lambda secret: "------",
            "LOGS": [],
            "append_log": self.logs.append,
            "_run_account_worker": fake_worker,
            "get_profile_dir": forbidden,
            "_launch_on_interactive_desktop": forbidden,
        }
        if "def _require_unlocked_account(" in (ROOT / "app.py").read_text():
            extract("app.py", "_require_unlocked_account", self.ns)

    def route(self, name):
        return extract("app.py", name, self.ns)

    async def assert_blocked(self, name, req, code=409):
        before = copy.deepcopy(self.config)
        with self.assertRaises(HttpError) as err:
            await self.route(name)(req)
        self.assertEqual(err.exception.status_code, code)
        self.assertEqual(self.scheduled, [])
        self.assertEqual(self.saves, [])
        self.assertEqual(self.config, before)

    async def test_single_blocks_locked_account_at_every_start_step(self):
        for step in range(1, 6):
            with self.subTest(step=step):
                await self.assert_blocked("run_single", SimpleNamespace(account_id="fixture", start_step=step))

    async def test_single_blocks_completed_account(self):
        self.config["accounts"] = [fake_account(status="completed")]
        await self.assert_blocked("run_single", SimpleNamespace(account_id="fixture", start_step=1))

    async def test_single_missing_account_does_not_queue(self):
        await self.assert_blocked("run_single", SimpleNamespace(account_id="absent", start_step=1), 404)

    async def test_pending_negative_control_queues_only_a_fake(self):
        self.config["accounts"] = [fake_account()]
        result = await self.route("run_single")(SimpleNamespace(account_id="fixture", start_step=1))
        self.assertTrue(result["ok"])
        self.assertEqual(self.scheduled, ["fake_worker"])

    async def test_reset_preserves_locked_account(self):
        await self.assert_blocked("reset_account", SimpleNamespace(account_id="fixture"))

    async def test_reset_cannot_remove_completed_protection(self):
        self.config["accounts"] = [fake_account(status="completed")]
        await self.assert_blocked("reset_account", SimpleNamespace(account_id="fixture"))

    async def test_manual_browser_blocks_locked_account(self):
        await self.assert_blocked("open_browser_manual", SimpleNamespace(account_id="fixture"))

    async def test_default_batch_blocks_when_every_account_is_locked(self):
        await self.assert_blocked("run_batch", SimpleNamespace(account_ids=None, start_step=1))

    async def test_explicit_batch_cannot_override_lock(self):
        await self.assert_blocked("run_batch", SimpleNamespace(account_ids=["fixture"], start_step=1))

    async def test_batch_unknown_id_does_not_queue(self):
        await self.assert_blocked("run_batch", SimpleNamespace(account_ids=["absent"], start_step=1), 404)

    async def test_mixed_batch_excludes_locked_and_completed(self):
        self.config["accounts"] += [fake_account("done", status="completed"), fake_account("pending")]
        result = await self.route("run_batch")(SimpleNamespace(account_ids=None, start_step=1))
        self.assertEqual(result["queued"], ["pending"])
        self.assertEqual(set(result["skipped_locked"]), {"fixture", "done"})
        self.assertEqual(self.scheduled, ["_batch_runner"])

    async def test_explicit_mixed_batch_excludes_locked_account(self):
        self.config["accounts"].append(fake_account("pending"))
        result = await self.route("run_batch")(SimpleNamespace(account_ids=["fixture", "pending"], start_step=5))
        self.assertEqual(result["queued"], ["pending"])
        self.assertEqual(result["skipped_locked"], ["fixture"])

    async def test_state_exposes_lock_without_changing_old_error(self):
        self.config["accounts"][0].update(status="error", current_step=4)
        result = await self.route("get_state")()
        account = result["accounts"][0]
        self.assertTrue(account["run_locked"])
        self.assertIn("locked", account["run_lock_reason"])
        self.assertEqual(account["status"], "error")
        self.assertEqual(account["current_step"], 4)
        self.assertEqual(self.saves, [])

    async def test_reset_pending_negative_control(self):
        self.config["accounts"] = [fake_account(current_step=1)]
        await self.route("reset_account")(SimpleNamespace(account_id="fixture"))
        self.assertEqual(self.config["accounts"][0]["current_step"], 0)
        self.assertEqual(self.scheduled, [])

    async def test_worker_rechecks_lock_before_importing_engine(self):
        before = copy.deepcopy(self.config)
        await self.route("_run_account_worker")("fixture", start_step=1)
        self.assertEqual(self.config, before)
        self.assertEqual(self.scheduled, [])
        self.assertTrue(any("blocked" in msg.lower() for msg in self.logs))


class EngineGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_pipeline_returns_before_credentials_or_browser_at_all_steps(self):
        ns = {
            "__builtins__": {**vars(builtins), "__import__": forbidden},
            "account_run_lock_reason": account_run_lock_reason,
            "re": SimpleNamespace(sub=forbidden),
            "get_profile_dir": forbidden,
            "resolve_account_proxy": forbidden,
            "async_playwright": forbidden,
        }
        run = extract("automation_engine.py", "run_pipeline", ns, "GoogleUltraAutomator")
        for account in (fake_account(automation_locked=True), fake_account(status="completed")):
            for step in range(1, 6):
                with self.subTest(status=account["status"], step=step):
                    logs = []
                    obj = SimpleNamespace(account=account, card=NoCredentials(), log=logs.append, update_state=forbidden)
                    await run(obj, start_step=step)
                    self.assertTrue(any("blocked" in msg.lower() for msg in logs))


if __name__ == "__main__":
    unittest.main()
