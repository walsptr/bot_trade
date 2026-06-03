import os
import sys
from pathlib import Path


def _env_truthy(name: str) -> bool:
    v = os.getenv(name)
    if v is None:
        return False
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_mode(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("backtest", "bt"):
        return "backtest"
    return "live"


def main() -> None:
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root / "src"))

    from mt5bot.backtest_runner import run_backtest
    from mt5bot.config import load_config
    from mt5bot.env import load_env
    from mt5bot.live_runner import run_live

    load_env(project_root)
    mode = _normalize_mode(os.getenv("MODE") or "live")
    cfg = load_config(project_root, mode)

    if mode == "backtest":
        run_backtest(cfg)
        return

    if _env_truthy("RUN_ONCE"):
        os.environ["RUN_ONCE"] = "1"
    run_live(cfg)


if __name__ == "__main__":
    main()

