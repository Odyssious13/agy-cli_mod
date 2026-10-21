---
name: agy-api-subagent
description: "Trigger when delegating mechanical coding, file editing, scouting, test runs, or subagent tasks to agy-api (gemini-3.5-flash-lite on Free or Paid API key) WITHOUT calling Argon unless explicitly requested."
---

# `agy-api` Subagent Skill — Fast `gemini-3.5-flash-lite` Worker (Free & Paid Tier)

Use `agy-api` (`gemini-3.5-flash-lite`) as a standalone, low-cost/free CLI worker for mechanical file edits, code scouting, test execution, git operations, or optionally chaining with `argon-subagent` when explicitly requested.

## 1. Express Commands (Available Anywhere in `/mnt/storage/*`)
- `agy-api` — Launch interactive `gemini-3.5-flash-lite` TUI.
- `agy-api -p "<prompt>"` — Run a headless one-shot task with `gemini-3.5-flash-lite` (**does NOT call Argon** unless your prompt explicitly says `"use argon"`).
- `agy-free` — Switch `agy-api` to `FREE_GEMINI_API_KEY` (enforces 5 RPM & 250k TPM sliding-window guard automatically).
- `agy-paid` — Switch `agy-api` to `PAID_GEMINI_API_KEY` (disables Free-Tier rate-limit sleep).
- `agy-key` — Show the currently active `agy-api` key tier (`FREE` or `PAID`) and recent usage.

## 2. Free-Tier Rate Limits (5 RPM & 250,000 TPM) & Efficiency Rules
When `agy-api` is running on the **FREE** key (`agy-free`):
1. **Automatic Proxy Enforcement:** `/mnt/storage/.agy-api-workspace/model_proxy.py` tracks a 61-second sliding window across all processes and enforces **5 Requests Per Minute (5 RPM)** and **240,000 Tokens Per Minute (250k TPM cap)**.
2. **Run Inside the Target Project Directory (`cd /mnt/storage/projects/<repo>`):**
   - Running `agy-api` inside a project directory sends only **~7,000 tokens** (~2,950 uncached + ~4,050 cached), whereas running from `/mnt/storage` root loads `/mnt/storage/AGENTS.md` (~14,700 tokens).
3. **Conserve Tool Turns (Stay Under 5 RPM):**
   - Every tool call inside `agy-api` costs 1 request toward the 5 RPM limit.
   - Batch shell commands and file operations so standalone tasks finish in **1 to 3 tool turns** without triggering a 60-second rate-limit wait.

## 3. Standalone Delegation Format (No Argon — $0 on Free Tier)
When `claude`, `codex`, or `agy` delegates a normal task to `agy-api` **without** Argon:
```bash
cd /mnt/storage/projects/<project-dir> && agy-api -p "In /mnt/storage/projects/<project-dir>/<file>, implement <task> and run <test-command>."
```

## 4. Optional Chained Delegation Format (Only When User Explicitly Requests Argon)
If (and only if) the user asks to combine `agy-api` (cheap hands) with `argon-subagent` (paid brain), pass explicit `--files` so `agy-api` skips Phase 1 scouting and runs `call_argon.py` on Turn 1:
```bash
cd /mnt/storage/projects/<project-dir> && agy-api -p "Use argon (thinking-level: medium) with --files /mnt/storage/<path1> to fix: <issue>. Apply Argon's edits and verify locally."
```
