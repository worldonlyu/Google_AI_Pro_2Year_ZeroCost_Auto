"""Local-only safeguards against rerunning completed or explicitly locked accounts."""


def account_run_lock_reason(account: dict) -> str | None:
    """Check if an account is locked from running automation."""
    # A lock is independent of progress/status; resetting progress must not clear it.
    if account.get("automation_locked"):
        return "Account is locked against reuse. No login or subscription actions will run."
    if account.get("status") == "completed":
        return "Completed accounts cannot be rerun or reset automatically."
    return None

