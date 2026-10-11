# Working on this repository (for coding agents)

Read `README.md` first. This is a Docker-only setup: OpenClaw `2026.9.8`
gateway + Jaeger, driven by `setup.ps1` on Windows. Work from the repository
root.

- Inspect `docker compose ps`, ports 18789/16686 and existing volumes before
  starting anything. Reuse the existing `openclaw-state` volume; never run
  `docker compose down -v` unless the user asks to reset.
- The tracked `config/openclaw.json` is the source of truth. Apply changes with
  `setup.ps1` (it runs `docker/init.py`, which preserves runtime keys such as
  `auth` and `commands`). Validate with
  `docker compose exec openclaw openclaw config validate`.
- Agents: `main` (Coordinator), `researcher`, `writer`. Workspaces are
  `/project/openclaw/workspace` and `/project/openclaw/workspace/agents/<id>`
  inside the container, on the `openclaw-workspace` volume (Windows bind
  mounts break OpenClaw's atomic writes). `setup.ps1` syncs tracked
  instructions from `openclaw/workspace/` into it and never overwrites
  `MEMORY.md`, `memory/`, `reports/` or `output/`.
- Tool boundaries are per-agent `tools.deny`. Global `tools.deny` always wins,
  and spawned children also inherit the parent's policy, so never deny
  `group:web` globally or on `main`.
- Web search uses the pinned `@openclaw/parallel-plugin@2026.9.8`
  (`parallel-free`, no key); OpenAI's hosted search is not available to
  spawned sub-agents.
- Secrets live only in `.local/openclaw.env` and the Docker volume. Never print
  them, never put them in chat, screenshots, commits, or the tracked config;
  use `${VAR}` or env SecretRefs. Pipe keys on stdin inside the container.
- Keep host ports bound to `127.0.0.1`. Telegram stays on pairing; A2A peers
  need bearer tokens.
- Live memory (`MEMORY.md`, `memory/`, `reports/`, `output/`) is ignored by Git;
  only `MEMORY.template.md` files are tracked.
- Before committing: `python -m unittest discover -s scripts -p "test_*.py"`,
  `python scripts/check_config_privacy.py`; before publishing also
  `python scripts/check_publication.py --history`.
- Record observed versions, executed checks and remaining failures in
  `setup-notes.md`. Distinguish executed checks from instructions.
