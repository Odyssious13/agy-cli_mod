---
name: argon-subagent
description: "Trigger ONLY when the user explicitly says 'use argon', 'ask argon', or 'run argon' (case-insensitive). Never invoke automatically. Calls Paid-Tier gemini-4-argon via call_argon.py with 95% prefix cache optimization."
---

# Argon (API) Subagent Skill — Paid-Tier `gemini-4-argon` (`call_argon.py`)

Whenever the user or orchestrator explicitly asks to **"use argon"**, **"ask argon"**, or **"run argon"**, execute the phases below. Do NOT invoke this skill for general `agy-api` (`gemini-3.5-flash-lite`) tasks unless Argon is explicitly requested.

## API KEY RULE (PAID TIER ONLY)
- `gemini-4-argon` is **NOT available on the Free Tier**.
- `call_argon.py` strictly uses `ARGON_API_KEY` or `PAID_GEMINI_API_KEY` from `/mnt/storage/.env` ($2.00/1M uncached input, $0.10/1M cached input, $10.00/1M output) and blocks `FREE_GEMINI_API_KEY`.
- Can be invoked directly by `claude`, `codex`, `agy`, or delegated through `agy-api` (see `agy-api-subagent` when chaining).

## PHASE 1: Zero-Turn Fast-Path or Minimal Scouting
1. **Zero-Turn Fast-Path:** If target `/mnt/storage/...` file paths are already known or provided via `--files`, **SKIP file reading completely (0 turns)**—`call_argon.py` reads files directly from disk in Python.
2. **Fallback Scouting:** If file paths are unknown, spend at most **2 tool turns** (`rg` / `find`) locating the **1 to 6 target files** on `/mnt/storage`.
3. **Announce Before Calling:** State the target `/mnt/storage` files, `--thinking-level`, and `--max-cost`.

## PHASE 2: Maximum Prefix-Cache Invocation (`call_argon.py`)
Invoke `call_argon.py` **ONCE** via bash:

```bash
python3 /mnt/storage/.gemini/antigravity/skills/argon-subagent/scripts/call_argon.py \
  --caller <claude|agy|agy-api|codex> \
  --thinking-level <low|medium|high> \
  --max-cost <usd_limit_default_0.50> \
  --timeout-seconds 180 \
  --pinned-files <optional-unchanging-reference-files-on-mnt-storage> \
  --files <1-to-6-target-file-paths-on-mnt-storage> \
  --query "<concise problem statement, error logs, and specific goal>"
```

### Mandatory Rules for 95% Prefix Caching & Low API Spend:
1. **Never Paste File Contents in `--query`:** Pass code files via `--files` (auto-sorted oldest-to-newest `st_mtime`) and unchanging reference docs via `--pinned-files`. Keep `--query` strictly for the dynamic question/error trace at the tail.
2. **No Visual Verification Loops with Argon:** Never pass screenshots or re-call Argon for visual checks—verify locally.
3. **Sticky File List on Follow-Ups:** Keep the same `--files` / `--pinned-files` list on follow-up calls within 15 minutes so the token prefix matches byte-for-byte.

## PHASE 3: Immediate Surgical Edit Application & Local Verification
1. Report Argon's root-cause summary, `Input Cache Hit %`, and `Call API Cost`.
2. Apply Argon's `SEARCH / REPLACE` blocks immediately on `/mnt/storage`.
3. Run verification tests locally while enforcing headless SD rules (no `:0` display windows, `Xvfb :96` / `SD_QUIET=1`, `SDL_AUDIODRIVER=dummy`, serve on network ports).
