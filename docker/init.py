#!/usr/bin/env python3
"""Install the tracked OpenClaw config into the Docker state volume.

Runs inside the openclaw container as root (see setup.ps1):

    docker compose run --rm --no-deps --user 0 --entrypoint python3 openclaw /project/docker/init.py

Safe to repeat: the agent roster, tool policy, channels and tracing come from
config/openclaw.json; account state that OpenClaw writes at runtime (auth
profiles, command owner, wizard metadata) is kept from the existing live config.
"""
import json
import os
from pathlib import Path
import shutil
import sys

TRACKED = Path("/project/config/openclaw.json")
STATE = Path("/home/node/.openclaw")
LIVE = STATE / "openclaw.json"
# Keys OpenClaw manages at runtime; never overwritten by the tracked file.
RUNTIME_KEYS = ("auth", "commands", "meta", "wizard", "approvals")
NODE_UID = NODE_GID = 1000
WORKSPACE_SRC = Path("/project/workspace-src")
WORKSPACE = Path("/project/openclaw/workspace")
LIVE_DIRS = {"memory", "reports", "output", ".openclaw"}


def env_values(path):
    """Parse a dotenv file without executing it."""
    path = Path(path)
    if not path.is_file():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        result[key.strip()] = value
    return result


def build_config(tracked, live, environ):
    data = json.loads(json.dumps(tracked))
    for key in RUNTIME_KEYS:
        if key in live:
            data[key] = live[key]
    channels = data.get("channels", {})
    # Without a token the Telegram channel would fail at startup; keep it off
    # until the token is added and this script runs again.
    if "telegram" in channels and not environ.get("TELEGRAM_BOT_TOKEN"):
        channels["telegram"]["enabled"] = False
    if "a2a" in channels and not environ.get("A2A_CLIENT_TOKEN"):
        channels["a2a"]["enabled"] = False
    return data


def is_live_data(relative):
    """Files the agents own at runtime; never overwritten from the repository."""
    parts = relative.parts
    return relative.name == "MEMORY.md" or any(p in LIVE_DIRS for p in parts)


def sync_workspace(source=WORKSPACE_SRC, target=WORKSPACE):
    """Refresh tracked instructions in the workspace volume; keep agent memory.

    Instruction files (AGENTS.md, SOUL.md, ...) always follow the repository.
    Live data (MEMORY.md, memory/, reports/, output/) is copied only when the
    volume does not have it yet, which also migrates memory from an older
    bind-mounted workspace. Each agent without MEMORY.md gets its template.
    """
    if not source.is_dir():
        return
    updated = 0
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if is_live_data(relative) and destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        updated += 1
    for template in target.rglob("MEMORY.template.md"):
        memory = template.with_name("MEMORY.md")
        if not memory.exists():
            shutil.copyfile(template, memory)
            print(f"Created {memory.relative_to(target)} from its template.")
    for root, directories, files in os.walk(target):
        for name in (root, *(os.path.join(root, item) for item in directories + files)):
            os.chown(name, NODE_UID, NODE_GID)
    print(f"Workspace volume synced from the repository ({updated} files copied; memory kept).")


def main():
    missing = [key for key in ("OPENCLAW_GATEWAY_TOKEN", "OPENAI_API_KEY") if not os.environ.get(key)]
    if missing:
        raise ValueError("Fill " + ", ".join(missing) + " in .local/openclaw.env first.")
    tracked = json.loads(TRACKED.read_text(encoding="utf-8"))
    live = json.loads(LIVE.read_text(encoding="utf-8")) if LIVE.is_file() else {}
    data = build_config(tracked, live, os.environ)
    STATE.mkdir(parents=True, exist_ok=True)
    temporary = LIVE.with_suffix(".json.tmp-init")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(LIVE)
    for path in (STATE, LIVE):
        os.chown(path, NODE_UID, NODE_GID)
    STATE.chmod(0o700)
    LIVE.chmod(0o600)
    sync_workspace()
    telegram = data.get("channels", {}).get("telegram", {}).get("enabled")
    print("OpenClaw config installed: agents main, researcher, writer; tracing to Jaeger.")
    print("Telegram channel: " + ("enabled" if telegram else "disabled (TELEGRAM_BOT_TOKEN is empty)"))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"Stopped: {error}")
