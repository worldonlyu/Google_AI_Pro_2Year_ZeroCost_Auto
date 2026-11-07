import asyncio
import copy
import json
import os
import re
import subprocess
import time
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from account_safety import account_run_lock_reason
from automation_engine import (
    GoogleUltraAutomator,
    LocalHttpProxyAuthBridge,
    get_totp,
    get_profile_dir,
    resolve_account_proxy,
    parse_proxy_string,
    delete_account_files,
    find_chrome_path,
    CHROME_PATH,
    CHROME_EXTRA_ARGS,
    BASE_DIR,
    PROFILES_DIR,
    SCREENSHOTS_DIR,
)

CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
CONFIG_EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(PROFILES_DIR, exist_ok=True)

app = FastAPI(title="Google AI Pro (5 TB) 零成本两年全自动控制台")
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")

# Global runtime state
LOGS: List[str] = [
    f"[{time.strftime('%H:%M:%S')}] [SYSTEM] 🚀 Google AI Pro (5 TB) 零成本两年 (US$0.00 -> 24个月) 全自动控制台已就绪！"
]
ACTIVE_TASKS: Dict[str, GoogleUltraAutomator] = {}
BATCH_RUNNING: bool = False
STOP_BATCH: bool = False

DEFAULT_CONFIG: Dict[str, Any] = {
    "target_region": "US",
    "target_plan": "pro_2year_zero",
    "auto_cancel": True,
    "proxy_template": "",
    "card": {
        "number": "",
        "exp_month": "",
        "exp_year": "",
        "cvc": "",
        "holder": "",
        "address_line1": "700 SW 5th Ave",
        "postal_code": "97201",
        "locality": "Portland",
        "province": "OR",
    },
    "accounts": [],
}


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_PATH):
        if os.path.exists(CONFIG_EXAMPLE_PATH):
            try:
                with open(CONFIG_EXAMPLE_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                save_config(cfg)
                return cfg
            except Exception:
                pass
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = json.loads(json.dumps(DEFAULT_CONFIG))
        save_config(data)
        return data

    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for k in ("target_region", "target_plan", "auto_cancel", "proxy_template", "accounts"):
        if k in data:
            merged[k] = data[k]
    if isinstance(data.get("card"), dict):
        merged["card"].update(data["card"])
    return merged


def save_config(cfg: Dict[str, Any]):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# Ensure config is initialized
load_config()


def append_log(line: str):
    print(line, flush=True)
    LOGS.append(line)
    if len(LOGS) > 1200:
        LOGS.pop(0)


class ConfigUpdateReq(BaseModel):
    target_region: str
    target_plan: str
    auto_cancel: bool
    proxy_template: str
    card: Dict[str, Any]


class AccountActionReq(BaseModel):
    account_id: str


class RunSingleReq(BaseModel):
    account_id: str
    start_step: int = 1


class RunBatchReq(BaseModel):
    account_ids: Optional[List[str]] = None
    start_step: int = 1


class ImportAccountsReq(BaseModel):
    text: str


class ProxyTestReq(BaseModel):
    proxy_template: str
    target_region: Optional[str] = "US"


def _require_unlocked_account(cfg: Dict[str, Any], account_id: str) -> Dict[str, Any]:
    account = next((a for a in cfg.get("accounts", []) if a["id"] == account_id), None)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    reason = account_run_lock_reason(account)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    return account


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(TEMPLATES_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/state")
async def get_state():
    cfg = load_config()
    rem_sec = 30 - (int(time.time()) % 30)
    accounts_out = []
    for acc in cfg.get("accounts", []):
        item = dict(acc)
        item["run_lock_reason"] = account_run_lock_reason(acc) or ""
        item["run_locked"] = bool(item["run_lock_reason"])
        try:
            item["totp_now"] = get_totp(acc.get("totp_secret", ""))
        except Exception:
            item["totp_now"] = "------"
        item["totp_rem"] = rem_sec
        item["is_running"] = acc["id"] in ACTIVE_TASKS
        accounts_out.append(item)

    return {
        "target_region": cfg.get("target_region", "US"),
        "target_plan": cfg.get("target_plan", "pro_2year_zero"),
        "auto_cancel": cfg.get("auto_cancel", True),
        "proxy_template": cfg.get("proxy_template", ""),
        "card": {
            "number": cfg.get("card", {}).get("number", ""),
            "exp_month": cfg.get("card", {}).get("exp_month", ""),
            "exp_year": cfg.get("card", {}).get("exp_year", ""),
            "cvc": cfg.get("card", {}).get("cvc", ""),
            "holder": cfg.get("card", {}).get("holder", ""),
            "address_line1": cfg.get("card", {}).get("address_line1", "700 SW 5th Ave"),
            "postal_code": cfg.get("card", {}).get("postal_code", "97201"),
            "locality": cfg.get("card", {}).get("locality", "Portland"),
            "province": cfg.get("card", {}).get("province", "OR"),
        },
        "accounts": accounts_out,
        "logs": LOGS,
        "batch_running": BATCH_RUNNING,
    }


@app.post("/api/config")
async def update_config(req: ConfigUpdateReq):
    cfg = load_config()
    cfg["target_region"] = req.target_region.upper()
    cfg["target_plan"] = req.target_plan
    cfg["auto_cancel"] = req.auto_cancel
    cfg["proxy_template"] = req.proxy_template.strip()
    cfg["card"] = req.card
    save_config(cfg)
    append_log(f"[{time.strftime('%H:%M:%S')}] [CONFIG] ✅ 已保存配置 (目标地区: {req.target_region} | 代理模板: {'已启用' if req.proxy_template.strip() else '系统默认'})")
    return {"ok": True}


@app.post("/api/proxy/test")
async def test_proxy(req: ProxyTestReq):
    cfg = load_config()
    tpl = req.proxy_template.strip() or cfg.get("proxy_template", "").strip()
    region = (req.target_region or cfg.get("target_region") or "US").upper()
    resolved = resolve_account_proxy({"id": f"probe{int(time.time())%1000}", "email": "probe@gmail.com"}, region, tpl)
    if not resolved:
        return {"ok": False, "message": "未填写代理模板"}

    def _sync_probe():
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": resolved, "https": resolved}))
        req_obj = urllib.request.Request("http://ip-api.com/json/?fields=status,message,country,countryCode,city,org,query", headers={"User-Agent": "Mozilla/5.0"})
        with opener.open(req_obj, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = await asyncio.to_thread(_sync_probe)
        if data.get("status") != "success":
            return {"ok": False, "message": f"IP API 返回异常: {data.get('message', '未知错误')}"}

        bal_gb = None
        m_sess = re.search(r"sess-([a-zA-Z0-9]+)", resolved)
        if m_sess:
            sess_key = m_sess.group(1)
            bal_gb = LocalHttpProxyAuthBridge._cached_balances.get(sess_key)

        ip = data.get("query", "")
        country = data.get("country", "")
        cc = data.get("countryCode", "")
        city = data.get("city", "")
        org = data.get("connection", {}).get("org", "")
        flag = "🇺🇸" if cc == "US" else ("🇧🇴" if cc == "BO" else ("🇹🇷" if cc == "TR" else "🌐"))
        bal_str = f" | FloppyData 剩余流量: {bal_gb} GB" if bal_gb is not None else ""
        msg = f"{flag} 连通成功！出口 IP: {ip} ({country} · {city} | {org}){bal_str}"
        append_log(f"[{time.strftime('%H:%M:%S')}] [PROXY] ✅ {msg}")
        return {"ok": True, "message": msg, "ip": ip, "country_code": cc, "balance_gb": bal_gb}
    except Exception as e:
        err = f"代理测试失败: {e}"
        append_log(f"[{time.strftime('%H:%M:%S')}] [PROXY] ❌ {err}")
        return {"ok": False, "message": err}


@app.post("/api/accounts/import")
async def import_accounts(req: ImportAccountsReq):
    raw_lines = [l.strip() for l in req.text.splitlines() if l.strip()]
    if not raw_lines:
        return {"ok": False, "message": "导入内容为空"}

    cfg = load_config()
    existing = cfg.get("accounts", [])
    existing_emails = {a.get("email", "").strip().lower() for a in existing if a.get("email")}
    added = 0

    for idx, line in enumerate(raw_lines):
        line = line.replace(",", "----").replace("\t", "----")
        parts = [p.strip() for p in line.split("----") if p.strip()]
        if not parts:
            continue

        email = parts[0]
        password = parts[1] if len(parts) > 1 else ""
        recovery_or_totp = parts[2] if len(parts) > 2 else ""
        extra = parts[3] if len(parts) > 3 else ""
        proxy_str = parts[4] if len(parts) > 4 else ""

        totp_secret = ""
        recovery_email = ""

        candidates = [recovery_or_totp, extra]
        for c in candidates:
            if not c:
                continue
            cleaned = c.replace(" ", "").upper()
            if len(cleaned) in (16, 26, 32) and re.fullmatch(r"[A-Z2-7]+", cleaned):
                totp_secret = cleaned
            elif "@" in c:
                recovery_email = c
            elif ("://" in c or ":" in c) and not proxy_str:
                proxy_str = c

        norm_email = email.lower()
        if norm_email in existing_emails:
            for acc in existing:
                if acc.get("email", "").strip().lower() == norm_email:
                    if password:
                        acc["password"] = password
                    if totp_secret:
                        acc["totp_secret"] = totp_secret
                    if recovery_email:
                        acc["recovery_email"] = recovery_email
                    if proxy_str:
                        acc["proxy"] = proxy_str
            continue

        acc_id = f"acc_{len(existing) + 1:02d}"
        existing.append(
            {
                "id": acc_id,
                "email": email,
                "password": password,
                "recovery_email": recovery_email,
                "totp_secret": totp_secret,
                "proxy": proxy_str,
                "ip_info": "",
                "status": "pending",
                "current_step": 0,
                "step_message": "Newly imported account (pending)",
                "expiry_date": "-",
                "last_screenshot": "",
            }
        )
        existing_emails.add(norm_email)
        added += 1

    cfg["accounts"] = existing
    save_config(cfg)
    append_log(f"[{time.strftime('%H:%M:%S')}] [IMPORT] ✅ Imported/updated {added} account(s) ({len(existing)} total)")
    return {"ok": True, "added": added, "total": len(existing)}


@app.post("/api/accounts/delete")
async def delete_account(req: AccountActionReq):
    if req.account_id in ACTIVE_TASKS:
        raise HTTPException(status_code=400, detail="This account is currently running. Please stop the task first.")
    cfg = load_config()
    accounts = cfg.get("accounts", [])
    target_acc = next((a for a in accounts if a.get("id") == req.account_id), None)
    cfg["accounts"] = [a for a in accounts if a.get("id") != req.account_id]
    save_config(cfg)

    old_bridge = MANUAL_BRIDGES.pop(req.account_id, None)
    if old_bridge:
        try:
            await old_bridge.stop()
        except Exception:
            pass

    acc_email = (target_acc.get("email") if target_acc else "") or ""
    delete_account_files(req.account_id, acc_email)
    append_log(f"[{time.strftime('%H:%M:%S')}] [ACCOUNT] 🗑️ Removed account {req.account_id} and cleaned related files")
    return {"ok": True}


@app.post("/api/accounts/reset")
async def reset_account(req: AccountActionReq):
    if req.account_id in ACTIVE_TASKS:
        raise HTTPException(status_code=409, detail="Stop this account before resetting it")
    cfg = load_config()
    a = _require_unlocked_account(cfg, req.account_id)
    a["status"] = "pending"
    a["current_step"] = 0
    a["step_message"] = "State reset (pending)"
    save_config(cfg)
    append_log(f"[{time.strftime('%H:%M:%S')}] [ACCOUNT] 🔄 Reset account {req.account_id} to pending")
    return {"ok": True}


async def _run_account_worker(account_id: str, start_step: int = 1, port: int = 9320):
    cfg = load_config()
    target_acc = None
    for a in cfg.get("accounts", []):
        if a["id"] == account_id:
            target_acc = a
            break
    if not target_acc:
        return

    reason = account_run_lock_reason(target_acc)
    if reason:
        append_log(f"[{time.strftime('%H:%M:%S')}] [GUARD] Run blocked for {account_id}: {reason}")
        return

    import importlib
    import automation_engine
    importlib.reload(automation_engine)

    def on_state_patch(patch: Dict[str, Any]):
        c = load_config()
        for acc_item in c.get("accounts", []):
            if acc_item["id"] == account_id:
                acc_item.update(patch)
                break
        save_config(c)

    automator = automation_engine.GoogleUltraAutomator(
        account=target_acc,
        card=cfg.get("card", {}),
        target_region=cfg.get("target_region", "US"),
        target_plan=cfg.get("target_plan", "pro_2year_zero"),
        auto_cancel=cfg.get("auto_cancel", True),
        proxy_template=cfg.get("proxy_template", ""),
        port=port,
        logger=append_log,
        state_updater=on_state_patch,
    )

    ACTIVE_TASKS[account_id] = automator
    try:
        await automator.run_pipeline(start_step=start_step)
    finally:
        ACTIVE_TASKS.pop(account_id, None)


@app.post("/api/run/single")
async def run_single(req: RunSingleReq):
    if req.account_id in ACTIVE_TASKS:
        raise HTTPException(status_code=400, detail="This account is already running")
    _require_unlocked_account(load_config(), req.account_id)
    port = 9320 + (len(ACTIVE_TASKS) % 10)
    asyncio.create_task(_run_account_worker(req.account_id, start_step=req.start_step, port=port))
    return {"ok": True}


@app.post("/api/run/batch")
async def run_batch(req: RunBatchReq):
    global BATCH_RUNNING, STOP_BATCH
    if BATCH_RUNNING:
        raise HTTPException(status_code=400, detail="The batch queue is already running")

    cfg = load_config()
    accounts = {a["id"]: a for a in cfg.get("accounts", [])}
    requested_ids = req.account_ids if req.account_ids is not None else list(accounts)
    if any(aid not in accounts for aid in requested_ids):
        raise HTTPException(status_code=404, detail="A requested account was not found")

    skipped_locked = [aid for aid in requested_ids if account_run_lock_reason(accounts[aid])]
    queue_ids = [aid for aid in requested_ids if not account_run_lock_reason(accounts[aid])]

    if not queue_ids:
        raise HTTPException(status_code=409, detail="No eligible accounts: locked or completed accounts cannot be run")

    async def _batch_runner():
        global BATCH_RUNNING, STOP_BATCH
        BATCH_RUNNING = True
        STOP_BATCH = False
        append_log(f"[{time.strftime('%H:%M:%S')}] [BATCH] 🚀 Starting batch queue: {queue_ids} (start step: Step {req.start_step})")
        try:
            for idx, aid in enumerate(queue_ids):
                if STOP_BATCH:
                    append_log(f"[{time.strftime('%H:%M:%S')}] [BATCH] ⏹ Batch queue stopped on user request")
                    break
                append_log(f"[{time.strftime('%H:%M:%S')}] [BATCH] ({idx+1}/{len(queue_ids)}) Processing account [{aid}]...")
                port = 9320 + (idx % 10)
                await _run_account_worker(aid, start_step=req.start_step, port=port)
                if idx < len(queue_ids) - 1 and not STOP_BATCH:
                    append_log(f"[{time.strftime('%H:%M:%S')}] [BATCH] ⏳ Waiting 6 seconds before next account...")
                    await asyncio.sleep(6)
        finally:
            BATCH_RUNNING = False
            STOP_BATCH = False
            append_log(f"[{time.strftime('%H:%M:%S')}] [BATCH] 🏁 Batch execution finished")

    asyncio.create_task(_batch_runner())
    return {"ok": True, "queued": queue_ids, "skipped_locked": skipped_locked}


@app.post("/api/stop")
async def stop_all(req: Optional[AccountActionReq] = None):
    global STOP_BATCH
    if req and req.account_id:
        automator = ACTIVE_TASKS.get(req.account_id)
        if automator:
            automator.stop()
            append_log(f"[{time.strftime('%H:%M:%S')}] [STOP] ⏹ Sent stop signal to account [{req.account_id}]")
    else:
        STOP_BATCH = True
        for aid, automator in list(ACTIVE_TASKS.items()):
            automator.stop()
        append_log(f"[{time.strftime('%H:%M:%S')}] [STOP] ⏹ Sent global stop command")
    return {"ok": True}


@app.post("/api/logs/clear")
async def clear_logs():
    LOGS.clear()
    return {"ok": True}


MANUAL_BRIDGES: Dict[str, LocalHttpProxyAuthBridge] = {}


def _launch_on_interactive_desktop(args: List[str]):
    """Launch a local browser process using standard subprocess.Popen without winsta0 injection."""
    subprocess.Popen(args)


@app.post("/api/open_browser")
async def open_browser_manual(req: AccountActionReq):
    cfg = load_config()
    target_acc = _require_unlocked_account(cfg, req.account_id)

    user_data_dir = get_profile_dir(target_acc["id"], target_acc["email"])
    target_region = cfg.get("target_region", "US")
    proxy_template = cfg.get("proxy_template", "")
    resolved_proxy = resolve_account_proxy(target_acc, target_region, proxy_template)
    parsed_proxy = parse_proxy_string(resolved_proxy)

    chrome_args = [
        CHROME_PATH,
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--enforce-webrtc-ip-permission-check",
        "--start-maximized",
        *CHROME_EXTRA_ARGS,
    ]

    if parsed_proxy:
        if parsed_proxy.get("username") and parsed_proxy.get("password"):
            old_bridge = MANUAL_BRIDGES.pop(target_acc["id"], None)
            if old_bridge:
                try:
                    await old_bridge.stop()
                except Exception:
                    pass

            bridge_port = 18880 + (int(hashlib.md5(target_acc["id"].encode()).hexdigest(), 16) % 1000)
            bridge = LocalHttpProxyAuthBridge(
                local_port=bridge_port,
                target_host=parsed_proxy["host"],
                target_port=parsed_proxy["port"],
                username=parsed_proxy["username"],
                password=parsed_proxy["password"],
            )
            await bridge.start()
            MANUAL_BRIDGES[target_acc["id"]] = bridge
            chrome_args.append(f"--proxy-server=http://127.0.0.1:{bridge_port}")
        else:
            p_url = f"{parsed_proxy['scheme']}://{parsed_proxy['host']}:{parsed_proxy['port']}"
            chrome_args.append(f"--proxy-server={p_url}")

    chrome_args.extend(
        [
            "https://one.google.com/plans?hl=zh-CN",
            "https://play.google.com/store/account/subscriptions?hl=zh-CN",
            "https://play.google.com/store/account/orderhistory?hl=zh-CN",
        ]
    )
    _launch_on_interactive_desktop(chrome_args)
    append_log(
        f"[{time.strftime('%H:%M:%S')}] [BROWSER] 🌐 已为您手动打开 [{target_acc['id']}] ({target_acc['email']}) 的专属 Chrome 窗口"
    )
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("🚀 Google AI Pro (5 TB) 2-Year Zero-Cost Automation Console")
    print("🌐 Console URL: http://127.0.0.1:8765")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8765)

