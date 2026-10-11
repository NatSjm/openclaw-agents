#!/usr/bin/env python3
"""A minimal external agent that talks to the Researcher over the A2A 1.0 protocol.

It discovers the gateway's public Agent Card, then sends an authenticated
JSON-RPC `SendMessage` task and prints the Researcher's answer. Standard
library only. The bearer token is read from the A2A_CLIENT_TOKEN environment
variable or from .local/openclaw.env and is never printed.

Run it in its own container on the compose network (no host Python needed):

    docker compose run --rm --no-deps -v ./scripts:/scripts:ro --entrypoint python3 openclaw \
        /scripts/a2a_client.py --url http://openclaw:18789 "What is the A2A protocol?"

or with Python on the host:

    python scripts/a2a_client.py "What is the A2A protocol?"
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

ENV_FILE = Path(__file__).resolve().parent.parent / ".local" / "openclaw.env"


def token():
    value = os.environ.get("A2A_CLIENT_TOKEN", "")
    if not value and ENV_FILE.is_file():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("A2A_CLIENT_TOKEN="):
                value = line.split("=", 1)[1].strip().strip("'\"")
    if not value:
        sys.exit("A2A_CLIENT_TOKEN is not set; run setup.ps1 first.")
    return value


def request(url, payload=None, bearer=None, timeout=330):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Content-Type", "application/json")
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())


def rpc(endpoint, bearer, method, params):
    reply = request(endpoint, {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method, "params": params}, bearer)
    if "error" in reply:
        sys.exit(f"A2A error {reply['error'].get('code')}: {reply['error'].get('message')}")
    return reply["result"]


def task_text(task):
    parts = [part.get("text", "") for artifact in task.get("artifacts", []) for part in artifact.get("parts", [])]
    return "\n".join(part for part in parts if part)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question", nargs="?", default="Find 3 recent, reputable sources that explain the Agent2Agent (A2A) protocol and summarise each in one line.")
    parser.add_argument("--url", default="http://127.0.0.1:18789", help="Gateway origin")
    args = parser.parse_args()
    bearer = token()

    card = request(args.url.rstrip("/") + "/.well-known/agent-card.json")
    interface = card["supportedInterfaces"][0]
    # The card advertises the origin the request came from; keep the caller's origin.
    endpoint = args.url.rstrip("/") + "/a2a/v1"
    skills = ", ".join(skill["id"] for skill in card.get("skills", []))
    print(f"[discover] Agent Card: {card['name']} | protocol {interface['protocolVersion']} {interface['protocolBinding']} | skills: {skills}")

    message = {"messageId": str(uuid.uuid4()), "role": "ROLE_USER", "parts": [{"text": args.question}]}
    print(f"[send] SendMessage -> {endpoint}")
    result = rpc(endpoint, bearer, "SendMessage", {"message": message, "configuration": {"returnImmediately": True}})
    task = result.get("task", result)
    print(f"[task] id={task['id']} state={task['status']['state']}")

    deadline = time.time() + 600
    while task["status"]["state"] in ("TASK_STATE_SUBMITTED", "TASK_STATE_WORKING") and time.time() < deadline:
        time.sleep(5)
        task = rpc(endpoint, bearer, "GetTask", {"id": task["id"]})
        task = task.get("task", task)
        print(f"[poll] state={task['status']['state']}")

    print("\n=== Researcher answer (via A2A) ===")
    print(task_text(task) or json.dumps(task.get("status"), indent=2))
    if task["status"]["state"] != "TASK_STATE_COMPLETED":
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as error:
        sys.exit(f"Cannot reach the gateway: {error}")
