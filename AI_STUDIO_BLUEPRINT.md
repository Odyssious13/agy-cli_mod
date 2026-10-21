# AI STUDIO MASTER BLUEPRINT: `agy-cli_mod` Custom TUI / GUI & Agent Orchestrator

## 0. CRITICAL DIRECTIVE FOR AI STUDIO (READ FIRST — DO NOT VIOLATE)
You are building a custom interface (TUI / Local GUI Dashboard) for **`agy-cli_mod`**, a strictly isolated, directory-scoped dual-stack wrapper around the Antigravity CLI (`agy`) and Google AI Studio Gemini API (`agy-api`).

### MANDATORY ARCHITECTURAL CONSTRAINTS (NON-NEGOTIABLE):
1. **NEVER Break or Replace the Scoped Installation Method (`install.sh` & `uninstall.sh`):**
   - This repository uses a custom **self-relocating, directory-scoped installer (`install.sh`)** and **zero-trace uninstaller (`uninstall.sh` / `bin/agy-uninstall`)**.
   - When a user clones this repo into any temporary folder (e.g., `~/test`) and runs `./install.sh`, the installer prompts for a **`TARGET_ROOT`** (e.g., `/mnt/storage` or `~/test2`), dynamically rewrites all `/mnt/storage` path references to `$TARGET_ROOT` via `sed`, registers `$TARGET_ROOT` in `~/.config/agy-scoped-roots.list`, installs a `~/.bashrc` `PROMPT_COMMAND` hook (`_agy_scoped_path_hook`), moves the repo into `$TARGET_ROOT/projects/agy-cli_mod`, and deletes the temporary clone directory.
   - **DO NOT** replace `install.sh` with a global `pip`, `npm`, or `apt` installer. Any new UI dependencies (such as `textual`, `rich`, or web assets) MUST be installed inside `$TARGET_ROOT/.agy-api-workspace/.venv` or `$TARGET_ROOT/.npm-global` so that `agy-uninstall` completely removes 100% of files with zero leftovers in `$HOME`.
2. **Strict Directory Jail (`PWD` Enforcement & Dynamic Root Resolution):**
   - Commands (`agy`, `agy-api`, `agy-models`, `agy-free`, `agy-paid`, `agy-key`, `agy-uninstall`, and any new UI command) are **ONLY accessible when the user's terminal `$PWD` is inside `$TARGET_ROOT` or its subdirectories**.
   - All conversation histories, SQLite databases, `.env` API keys, `usage.tsv` logs, and `rate_limit_state.json` files MUST live exclusively inside `$TARGET_ROOT/.agy-api-workspace` (for API mode) and `$TARGET_ROOT/.agy-workspace` (for OAuth mode). Nothing may ever write to the user's real `~/.gemini` or `~`.
   - In all Python/Bash code you generate, default the root path string to `/mnt/storage` (so `install.sh` can rewrite it via `sed "s@/mnt/storage@$TARGET_ROOT@g"`) OR resolve the root dynamically relative to the script's location (`Path(__file__).resolve().parents[1]`).

---

## 1. Purpose of This Application (What We Are Building & Why)

### The Problem This Solves
The base Antigravity CLI (`~/.local/bin/agy`) has four major limitations when used with Google AI Studio API keys:
1. **No Free-Tier Rate-Limit Pacing:** Google AI Studio Free Tier enforces strict rolling 60-second RPM and TPM limits (e.g., 15 RPM / 250K TPM on `gemini-3.5-flash-lite`, and 5 RPM / 250K TPM / 20 RPD on `gemini-3.8-flash` and `gemini-3.6-flash`). Without pacing, multi-step tool calls or large cached contexts immediately trigger HTTP 429 errors, causing the CLI to retry every 1 second and re-ingest 250K tokens in a violent stutter loop.
2. **Hardcoded TUI Model Slots & No Live Key Switching:** The native binary only exposes a fixed list of models in `/model`, burns tokens on hidden background title-generation calls, and cannot hot-swap between a Free API key and a Paid API key mid-session.
3. **No Live Quota or Spend Visibility:** The native TUI does not show rolling 60s RPM/TPM usage, daily RPD usage (which resets at **Midnight Pacific Time**), or exact Paid-tier dollar spend (`$`).
4. **Global `$HOME` Pollution:** Base `agy` writes everything to `~/.gemini`. We require strict per-drive/per-directory isolation so each target root (like `/mnt/storage`) has its own completely isolated workspace, keys, and conversation history.

### Our Solution (`agy-cli_mod`)
- **Dual-Stack Isolation:**
  - `agy`: Runs standard OAuth Antigravity CLI isolated to `$TARGET_ROOT/.agy-workspace`.
  - `agy-api`: Runs API-backed Antigravity CLI isolated to `$TARGET_ROOT/.agy-api-workspace` through our local Python proxy (`workspace/model_proxy.py`) and binary patcher (`workspace/patch_tui_binary.py`).
- **Smooth Rolling-Window Pacer & Auto-Spillover (`workspace/model_proxy.py`):**
  - Tracks exact rolling 65-second RPM and TPM usage in `rate_limit_state.json` (backfilling actual `promptTokenCount + cachedContentTokenCount + candidatesTokenCount` from SSE responses).
  - Enforces hard safety ceilings below Google's raw limits (**10 RPM / 175K TPM** for Flash-Lite; **3 RPM / 175K TPM** for 5-RPM models) with token-proportional request spacing and a 35-second cooldown lock on any HTTP 429.
  - Automatically spills over between `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite-preview` for a combined **20 safe RPM (30 raw) / 350K safe TPM (500K raw) / 1,000 RPD** workhorse pool.
  - Mocks hidden conversation title requests locally in `0ms` (`0` tokens used).
  - Injects the **Quota Guard (`skills/quota-guard/SKILL.md`)** instruction automatically on 5-RPM Free-Tier models so the agent batches bash commands or delegates legwork to a single `3.5-flash-lite` subagent.

---

## 2. Complete Repository File Map & How Every File Works

| Repo File | Target Location After `./install.sh` | Purpose & Behavior (Must Be Preserved) |
| :--- | :--- | :--- |
| `install.sh` | `$TARGET_ROOT/projects/agy-cli_mod/install.sh` | Interactive installer: prompts for `$TARGET_ROOT`, prompts for `FREE_GEMINI_API_KEY` / `PAID_GEMINI_API_KEY` / `ARGON_API_KEY` (allowing blank), rewrites `/mnt/storage` -> `$TARGET_ROOT`, registers scoped `$PATH` hook in `~/.bashrc`, moves repo to `$TARGET_ROOT/projects/agy-cli_mod`, deletes temp clone dir. |
| `uninstall.sh` | `$TARGET_ROOT/bin/agy-uninstall` | Interactive uninstaller with `[y/N]` confirmation: steps out of `$TARGET_ROOT`, deletes `bin/*`, `.agy-api-workspace`, `.agy-workspace`, `.claude-workspace`, `.npm-cache`, `.npm-global`, `.gemini`, `.env`, `projects/agy-cli_mod`, unregisters from `~/.config/agy-scoped-roots.list`, and removes `$TARGET_ROOT` if empty. |
| `sync-from-live.sh` | `$TARGET_ROOT/projects/agy-cli_mod/sync-from-live.sh` | Copies live edited scripts from `$TARGET_ROOT/bin` and `$TARGET_ROOT/.agy-api-workspace` back into the git repo for easy commits. |
| `bin/_sd-env.sh` | `$TARGET_ROOT/bin/_sd-env.sh` | Sets isolated `HOME`, `XDG_*`, `TMPDIR`, `NPM_CONFIG_PREFIX`, and `NPM_CONFIG_CACHE` inside `$TARGET_ROOT`. |
| `bin/_sd-quiet.sh` | `$TARGET_ROOT/bin/_sd-quiet.sh` | Prevents background agents from opening GUI windows or playing audio (`SDL_VIDEODRIVER=offscreen`, `PULSE_SERVER=unix:/nonexistent`). |
| `bin/agy` | `$TARGET_ROOT/bin/agy` | OAuth launcher with strict `PWD` guard (`case "$PWD/" in "$TARGET_ROOT/"*)`). |
| `bin/agy-api` | `$TARGET_ROOT/bin/agy-api` | API launcher with strict `PWD` guard, short model aliases (`-m 3.5-lite`, `-m 3.8`, `-m 3.6`, `model ...`), optional `-p`/quotes for headless prompts, proxy startup, and binary patching. |
| `bin/agy-models` | `$TARGET_ROOT/bin/agy-models` | Instant CLI table showing Google AI Studio Free-Tier limits, Pacer Hard Caps, Rolling 60s RPM/TPM, and Today's RPD since Midnight PT (`America/Los_Angeles`). |
| `bin/swap-key` (`agy-free`, `agy-paid`, `agy-key`) | `$TARGET_ROOT/bin/*` | Switches active `GEMINI_API_KEY` in `$TARGET_ROOT/.env` between `FREE_GEMINI_API_KEY` and `PAID_GEMINI_API_KEY`. |
| `workspace/model_proxy.py` | `$TARGET_ROOT/.agy-api-workspace/model_proxy.py` | Local HTTP/SSE proxy handling rate pacing, spillover, token/cost logging (`usage.tsv`), in-chat `!` commands (`!models`, `!model`, `!effort`, `!agy free`, `!agy paid`), and live 15-byte status bar updates. |
| `workspace/patch_tui_binary.py` | `$TARGET_ROOT/.agy-api-workspace/patch_tui_binary.py` | Patches `~/.local/bin/agy` into `$TARGET_ROOT/bin/agy-lite-bin` (renames `Gemini 3.7 Flash` slot to `G3.5 Flash-Lite`, sets `FREE:API-Tier` / `PAID:API-Creds` badge, and locates the 15-byte `? for shortcuts` statusbar offset). |
| `skills/*` | `$TARGET_ROOT/.gemini/antigravity/skills/*` | `quota-guard`, `agy-api-subagent`, and `argon-subagent` skills. |

---

## 3. Exact Google AI Studio Free-Tier Quotas & Pacer Hard Caps

All RPD quotas reset at **Midnight Pacific Time (`America/Los_Angeles`)**. Rolling RPM and TPM windows are tracked over **65 seconds** (`rate_limit_state.json`).

| Short CLI / `!model` Alias | Upstream API Model ID | Actual AI Studio Free Quota | Pacer Hard Cap (Safe Ceiling) | Paid Tier Pricing (In / Cache / Out per 1M) |
| :--- | :--- | :--- | :--- | :--- |
| `3.5-lite` / `3.5-flash-lite` | `gemini-3.5-flash-lite` | **15 RPM · 250K TPM · 500 RPD** | **10 RPM / 175K TPM** | $0.30 / $0.03 / $2.50 |
| `3.1-lite` / `3.1-flash-lite` | `gemini-3.1-flash-lite-preview` | **15 RPM · 250K TPM · 500 RPD** | **10 RPM / 175K TPM** | $0.25 / $0.025 / $1.50 |
| `2.5-lite` / `2.5-flash-lite` | `gemini-2.5-flash-lite` | **10 RPM · 250K TPM · 20 RPD** | **7 RPM / 175K TPM** | $0.10 / $0.025 / $0.40 |
| `3.8` / `3.8-flash` | `gemini-3.8-flash` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.75 / $0.075 / $3.75 |
| `3.6` / `3.6-flash` | `gemini-3.6-flash` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.30 / $0.03 / $2.50 |
| `3.0` / `3.0-flash` | `gemini-3-flash-preview` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.30 / $0.03 / $2.50 |
| `2.5` / `2.5-flash` | `gemini-2.5-flash` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.375 / $0.0375 / $1.875 |
| `gemma-31b` / `gemma-4-31b` | `gemma-4-31b-it` | **30 RPM · 16K TPM · 14,400 RPD** | **20 RPM / 12K TPM** | Free ($0.00) |
| `gemma-26b` / `gemma-4-26b` | `gemma-4-26b-a4b-it` | **30 RPM · 16K TPM · 14,400 RPD** | **20 RPM / 12K TPM** | Free ($0.00) |
| `3.1-pro` / `pro` | `gemini-3.1-pro-preview` | **0 Free (PAID KEY ONLY)** | Unlimited on Paid | $2.00 / $0.10 / $10.00 |
| `2.5-pro` | `gemini-2.5-pro` | **0 Free (PAID KEY ONLY)** | Unlimited on Paid | $1.25 / $0.125 / $10.00 |
| `argon` | `gemini-4-argon` | **0 Free (PAID KEY ONLY)** | Unlimited on Paid | $2.00 / $0.10 / $10.00 |

---

## 4. GUI / Custom TUI Design Specification for Google AI Studio

### A. Recommended Stack
- **Option 1 (Terminal-Native TUI via Python `Textual`):** Runs directly inside the user's Ghostty terminal (`bin/agy-tui` or `agy-api --tui`). Provides full mouse click support, live progress bars, modal dialogs, and streaming Markdown while respecting the terminal workflow.
- **Option 2 (Local Web/Desktop GUI Dashboard + Embedded Terminal):** If building a React/TypeScript AI Studio Web App, pair it with a lightweight local Python backend (`workspace/ui_server.py`) that reads/writes `$TARGET_ROOT/.env`, `$TARGET_ROOT/.agy-api-workspace/rate_limit_state.json`, and `$TARGET_ROOT/.agy-api-workspace/usage.tsv`, and proxies chat/tool execution through `workspace/model_proxy.py`.

### B. Required Visual Panels & Controls
1. **Top Control Header:**
   - **Scope Indicator Badge:** Displays active `TARGET_ROOT` (e.g., `SCOPE: /mnt/storage`) and current working directory (`$PWD`).
   - **One-Click Key Tier Toggle (`FREE` <-> `PAID`):** Toggles `GEMINI_API_KEY` in `$TARGET_ROOT/.env` (identical to `!agy free` / `!agy paid`) and updates the UI theme accent (Emerald Green for Free Tier, Amber Gold for Paid Tier).
   - **Model & Thinking Effort Dropdowns:**
     - Model selector showing all 9 Free-Tier models (and 3 Paid-Only models when Paid tier is active) with live RPD remaining badges.
     - Thinking effort selector: `0-think` (strips `thinkingConfig`), `low` (`1,024` tokens), `medium` (`8,192` tokens), `high` (`24,576` tokens).
2. **Live Rolling-Window Quota & Pacer HUD:**
   - **Rolling 60s RPM Meter:** Visual bar showing `current_rpm / hard_cap (raw_limit)` (e.g., `4 / 10 RPM (15 max)`).
   - **Rolling 60s TPM Meter:** Visual bar showing `current_tpm / 175K safe cap (250K raw)` with color transitions (Green < 120K, Yellow 120K-160K, Red > 160K).
   - **Pacer Countdown Banner:** When `_calc_model_wait()` spaces out a request or waits for cumulative tokens to expire from the 65-second window, display a smooth animated countdown bar (`Smoothing token rate: next request in 4.2s — 168K/175K TPM`) with a button to force-spillover or switch models.
   - **Midnight PT RPD Tracker:** Shows `Today RPD: X / Max` and `Resets in Xh Ym (Midnight PT)`.
   - **Paid Spend Tracker:** Shows `Session: $0.XXXX` and `Today (PT): $0.XXXX` plus `Cache Hit %`.
3. **Interactive Chat & Collapsible Tool/Subagent Viewport:**
   - Streaming Markdown chat with syntax-highlighted code blocks and copy buttons.
   - Collapsible `Thought Process` accordions showing exact thinking token count.
   - Collapsible `Tool Execution` cards (`bash`, `read_file`, `edit_file`, `3.5-flash-lite subagent`) showing duration and token cost per step.
4. **Settings & Key Manager Modal:**
   - Allows viewing/updating `FREE_GEMINI_API_KEY`, `PAID_GEMINI_API_KEY`, and `ARGON_API_KEY` inside `$TARGET_ROOT/.env` without leaving the UI.

### C. How New UI Files Must Integrate with `install.sh`, `uninstall.sh`, and `sync-from-live.sh`
- Place any new Python backend/TUI scripts inside `workspace/` (e.g., `workspace/agy_ui.py`) and any launcher script inside `bin/` (e.g., `bin/agy-ui`).
- Ensure `bin/agy-ui` begins with the exact same `PWD` guard as `bin/agy-api`:
  ```bash
  case "$PWD/" in
    /mnt/storage/*) ;;
    *) echo "[agy-ui] Blocked: restricted to /mnt/storage" >&2; exit 1 ;;
  esac
  ```
- Because `install.sh` automatically iterates over `for f in "$CLONE_DIR/bin/"*` and `for f in "$CLONE_DIR/workspace/"*` and runs `sed "s@/mnt/storage@$TARGET_ROOT@g"`, placing your files in `bin/` and `workspace/` guarantees they will automatically relocate and scope themselves to any `$TARGET_ROOT`!
- Add any new `bin/` or `workspace/` filenames to the loop lists in `uninstall.sh` and `sync-from-live.sh` so uninstallation and live-syncing remain 100% complete.
