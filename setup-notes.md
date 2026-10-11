# Setup notes and verification

## Versions

- OpenClaw `2026.9.8` (`ghcr.io/openclaw/openclaw:2026.9.8`, Node 24.21 inside)
- Jaeger `2.11.0` (`jaegertracing/jaeger:2.11.0`)
- Host: Windows 10 Pro 22H2, Docker Desktop (engine 29.8.1, WSL 2 backend,
  ~3.9 GB RAM for the Docker VM), Windows PowerShell 5.1

## History

This repository started as a workshop starter (OpenClaw nine-agent team plus
Hermes, GBrain, Paperclip, Discord and Tailscale helpers; macOS/Linux native
route). For the homework it was reduced to a three-agent research team that
runs on Windows through Docker only. The removed components are in the Git
history before the homework commit.

## Executed checks (2026-10-11)

Offline:

- `python -m unittest discover -s scripts -p "test_*.py"`: 11 tests passed
  (config boundaries, init idempotency and state preservation, privacy checks).
- `openclaw config validate` on the tracked config inside the pinned image:
  valid.
- `scripts/check_config_privacy.py`: passed.

Container self-test with a dummy OpenAI key, under a throwaway compose project
that was deleted afterwards:

- `docker/init.py` installed the config and created the three `MEMORY.md`
  files from templates; Telegram was disabled automatically without a token.
- `openclaw models auth paste-api-key --provider openai --agent <id>` stored
  an API-key profile for each agent from stdin (key not printed).
- Gateway reached `/healthz` `{"ok":true,"status":"live"}`; first start took
  about 2.5 minutes on this host. Loaded plugins included `a2a` and
  `diagnostics-otel`.
- `openclaw agents list`: Coordinator, Researcher (A2A route), Writer, all on
  `openai/gpt-5.5`.
- `/.well-known/agent-card.json` returned the A2A 1.0 card (JSON-RPC,
  skill `researcher`).
- `scripts/a2a_client.py` in its own container: discovery, `SendMessage`,
  `GetTask` polling and `TASK_STATE_COMPLETED` worked; the answer was the
  expected provider 401 because the key was a dummy.
- Jaeger received service `openclaw-research-team` with `openclaw.run`,
  `openclaw.harness.run`, `openclaw.model.call` (error), and
  `openclaw.message.processed` (channel `a2a`, outcome `error`) spans tagged
  `openclaw.agent=researcher`.

## Real-credential run (2026-10-11, OpenAI API key + Telegram bot)

Executed:

- [x] Telegram pairing approved; `Ready` smoke test via
      `openclaw agent --agent main` returned `Ready`.
- [x] Step 3: `agents list` and per-agent `tools` match the README; the Writer,
      asked to use the web, reported no web tools.
- [x] Step 4 report scenario through Telegram. Jaeger trace of one report:
      `message.processed` (channel `telegram`) → `main`: `memory_search`,
      `memory_get`, `sessions_spawn` → `researcher` run: `memory_search`,
      6× `web_search`, 15× `web_fetch` (1 failed fetch of an external page,
      recorded as an error span), `write` → `main`: `sessions_spawn` →
      `writer` run: `memory_search`, `memory_get`, `write`, `read` → `main`:
      `read`, 2× `write` (report + index), `read`. All runs `completed`.
- [x] Step 7: those spans are visible in Jaeger with `openclaw.agent` tags;
      `web_search`/`web_fetch` appear only under `researcher`.
- [x] Step 5: after `docker compose restart openclaw` and `/new` in
      Telegram, the Coordinator listed both earlier reports (topic, file,
      takeaway) and the saved format preferences (Ukrainian, ≤400 words,
      «Джерела» section), citing `memory/report-index.md` and `MEMORY.md`.
- [x] Step 6: `scripts/a2a_client.py` in its own container discovered the
      Agent Card and received a completed task from the Researcher with three
      dated, sourced findings about the A2A protocol.

Problems found and fixed during this run:

1. The first report was written without web research: the Coordinator's
   per-agent `group:web` deny was inherited by the spawned Researcher, and
   OpenAI's hosted search is not offered to spawned sub-agents. Fix: no web
   deny on `main`; managed `web_search` through the pinned key-free
   `@openclaw/parallel-plugin@2026.9.8` (`parallel-free`).
2. Every agent `write` first failed with `staged file publish failed`. On the
   Docker Desktop Windows bind mount (9p/drvfs), `fstat` on an open file
   handle returns `ENOENT` after the file is renamed, which breaks OpenClaw's
   atomic-publish check. Fix: the live workspace is the Docker volume
   `openclaw-workspace`; `docker/init.py` syncs tracked instructions into it
   and migrates existing memory once. After the fix, writes succeed first try.
3. A key saved in `.local/openclaw.env` is only picked up after rerunning
   `setup.ps1` (container recreate); documented in Troubleshooting.

## Known limits

- Jaeger stores traces in memory; they reset when its container restarts.
- A2A tasks are kept in gateway memory for 24 h and are lost on restart
  (OpenClaw limitation); streaming and cancel are not supported.
- First gateway start is slow on small Docker VMs (2–5 minutes).
