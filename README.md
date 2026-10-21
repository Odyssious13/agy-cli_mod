# `agy-cli_mod` — Scoped Dual-Stack Antigravity CLI, Rolling Rate-Limit Pacer & Multi-Agent Orchestrator

`agy-cli_mod` is a directory-scoped, zero-pollution mod stack and local HTTP/SSE proxy architecture for the Antigravity CLI (`agy`). It enables side-by-side operation of standard Google OAuth (`agy`) and Google AI Studio API (`agy-api`) workflows within a strictly enforced directory jail, complete with real-time binary HUD patching, deterministic rolling-window rate-limit pacing, automatic cross-model quota spillover, and hierarchical multi-agent delegation.

---

## Table of Contents
1. [Core Architecture & Application Purpose](#1-core-architecture--application-purpose)
2. [The Smooth Rolling-Window Rate Guard (Exact Algorithms)](#2-the-smooth-rolling-window-rate-guard-exact-algorithms)
3. [Model Catalog, AI Studio Quotas & Pacer Ceilings](#3-model-catalog-ai-studio-quotas--pacer-ceilings)
4. [Generalized Installation & Zero-Trace Uninstallation](#4-generalized-installation--zero-trace-uninstallation)
5. [Complete Command Reference (Where & How to Run)](#5-complete-command-reference-where--how-to-run)
6. [Multi-Agent Orchestration Workflows (Planner + Minions + Argon)](#6-multi-agent-orchestration-workflows-planner--minions--argon)
7. [Repository File Structure & Maintenance](#7-repository-file-structure--maintenance)

---

## 1. Core Architecture & Application Purpose

The base Antigravity CLI binary (`~/.local/bin/agy`) writes all configuration, caches, and conversation histories globally to `~/.gemini`, lacks client-side awareness of Google AI Studio Free-Tier rolling rate limits, and provides a fixed set of TUI model slots.

`agy-cli_mod` solves these limitations through five architectural layers:

- **Directory-Scoped Isolation (`PWD` Jail & Fake `$HOME`):**
  During installation, you choose a target root directory (`$TARGET_ROOT`, such as `/mnt/storage` or `/mnt/projects`). A dynamic `~/.bashrc` `PROMPT_COMMAND` hook (`_agy_scoped_path_hook`) places `$TARGET_ROOT/bin` onto your `$PATH` **if and only if** your terminal's current working directory (`$PWD`) is inside `$TARGET_ROOT` or one of its subdirectories. Every wrapper script also enforces a hard `PWD` guard and overrides `HOME`, `XDG_*`, `TMPDIR`, and `NPM_CONFIG_*` to keep 100% of state, conversation history, and caches inside `$TARGET_ROOT`.
- **Side-by-Side Dual Stack (`agy` vs. `agy-api`):**
  - **`agy` (OAuth Stack):** Runs the unmodified `~/.local/bin/agy` binary with `HOME=$TARGET_ROOT/.agy-workspace`, keeping your Google OAuth credentials and chat history isolated to that drive.
  - **`agy-api` (API Proxy Stack):** Clones and byte-patches `~/.local/bin/agy` into `$TARGET_ROOT/bin/agy-lite-bin`, boots a local multi-threaded HTTP/SSE proxy (`workspace/model_proxy.py`) on an ephemeral localhost port, and routes all Gemini API traffic through the proxy.
- **Byte-Accurate ELF Binary Patching (`workspace/patch_tui_binary.py`):**
  - Repurposes the TUI's `Gemini 3.7 Flash (Low/Medium/High)` menu slot into **`G3.5 Flash-Lite (Low/Medium/High)`**.
  - Replaces the top startup credential banner with **`FREE:API-Tier`** or **`PAID:API-Creds`**.
  - Locates the 15-byte bottom-left `? for shortcuts` string offset in the binary and turns it into a **live in-place Status Bar HUD** (`FREE 1/10R 18kT` or `PAID $0.0046 1R`) updated via shared kernel page cache.
- **Zero-Token Background Interception:**
  Intercepts hidden TUI background requests (such as automatic conversation title generation) and returns mocked SSE responses locally in `0ms` at `0` token cost.
- **Live In-Chat Bang (`!`) Commands:**
  Intercepts `!models`, `!model`, `!effort`, `!agy free`, and `!agy paid` directly inside the `agy-api` chat prompt, executing configuration changes and key hot-swaps in `0ms` without consuming API quota.

---

## 2. The Smooth Rolling-Window Rate Guard (Exact Algorithms)

Google AI Studio Free Tier enforces strict **rolling 60-second windows** for Requests Per Minute (`RPM`) and Input Tokens Per Minute (`TPM`), alongside a daily Requests Per Day (`RPD`) quota that resets at **Midnight Pacific Time (`America/Los_Angeles`)**.

Naive rate limiters fail on large agentic contexts because:
1. Waiting only for the *single oldest request* to expire wakes the client too early when a single expiring 4K-token turn does not free enough room for an incoming 28K-token cached turn.
2. Pre-flight byte estimates (`len(body) // 4`) drastically underestimate implicit/explicit cached token counts (`cachedContentTokenCount`), allowing requests to slip past pre-flight checks and hit upstream `HTTP 429` errors.
3. When `agy` receives an upstream `429`, its internal retry loop re-sends the entire 250K-token payload every 1 second, causing violent terminal stuttering.

`workspace/model_proxy.py` implements a **5-Stage Deterministic Rolling-Window Pacer** backed by an `fcntl.flock` cross-process state file (`$TARGET_ROOT/.agy-api-workspace/rate_limit_state.json`) so the main TUI and any concurrent subagents share one unified quota ledger.

### Stage 1: Conservative Hard Ceilings & 65-Second Safety Window
To prevent clock-skew or burst boundary collisions with Google's edge servers, the proxy tracks all requests over a **`WINDOW_SECONDS = 65.0`** rolling window and enforces hard ceilings strictly below Google's raw limits:
- **Workhorse Tier (`gemini-3.5-flash-lite`, `gemini-3.1-flash-lite-preview`):** Raw Limit = `15 RPM / 250,000 TPM` -> **Pacer Hard Cap = `10 RPM / 175,000 TPM`**.
- **Secondary Lite Tier (`gemini-2.5-flash-lite`):** Raw Limit = `10 RPM / 250,000 TPM` -> **Pacer Hard Cap = `7 RPM / 175,000 TPM`**.
- **High-Reasoning Flash Tier (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3-flash-preview`, `gemini-2.5-flash`):** Raw Limit = `5 RPM / 250,000 TPM` -> **Pacer Hard Cap = `3 RPM / 175,000 TPM`**.
- **Gemma 4 Tier (`gemma-4-31b-it`, `gemma-4-26b-a4b-it`):** Raw Limit = `30 RPM / 16,000 TPM` -> **Pacer Hard Cap = `20 RPM / 12,000 TPM`**.

### Stage 2: High-Water Pre-Flight Token Estimation & Post-Turn Backfill
1. **Pre-Flight Estimate Upgrade:** Before a request is sent, the initial byte estimate $E_{\text{raw}} = \lfloor \text{len}(\text{body}) / 3 \rfloor$ is compared against the maximum real token count recorded in the rolling 65-second window for that model ($T_{\max}$):
   $$E = \min\left(\text{hard\_tpm},\; \max\left(E_{\text{raw}},\; \lfloor 1.05 \times T_{\max} \rfloor\right)\right)$$
   This guarantees that multi-turn conversations with large cached contexts are never underestimated prior to dispatch.
2. **Post-Turn SSE Regex Backfill:** As the SSE stream returns from Google, the proxy extracts `promptTokenCount`, `cachedContentTokenCount`, `candidatesTokenCount`, and `thoughtsTokenCount` via regex. Upon stream completion, `record_turn_usage()` re-locks `rate_limit_state.json` and updates that slot's token entry with the exact total tokens billed by Google:
   $$T_{\text{actual}} = \text{promptTokenCount} + \text{cachedContentTokenCount} + \text{candidatesTokenCount} + \text{thoughtsTokenCount}$$

### Stage 3: Exact Cumulative Expiry Calculation (`_calc_model_wait`)
Let $H = [h_1, h_2, \dots, h_k]$ be the chronological list of active requests for model $M$ within the last $W = 65.0$ seconds, where each $h_i$ has timestamp $t_i$ and token count $T_i$. Let $R_{\text{used}} = k$ and $T_{\text{used}} = \sum_{i=1}^k T_i$.

The pacer computes four independent wait durations and takes their maximum:

1. **RPM Ceiling Wait ($W_{\text{rpm}}$):**
   If $R_{\text{used}} \ge \text{hard\_rpm}$, the number of requests that must expire is $n = R_{\text{used}} - \text{hard\_rpm} + 1$. The exact entry whose expiration frees a slot is $h_{n}$ (0-indexed `idx = used_rpm - hard_rpm`):
   $$W_{\text{rpm}} = \max\left(0.5,\; (t_{\text{idx}} + 65.0) - t_{\text{now}} + 0.25\right)$$
2. **Cumulative TPM Ceiling Wait ($W_{\text{tpm}}$):**
   If $T_{\text{used}} + E > \text{hard\_tpm}$, the pacer must free at least $\Delta T = (T_{\text{used}} + E) - \text{hard\_tpm}$ tokens. It walks chronologically through $h_1, h_2, \dots, h_m$ accumulating $\sum_{i=1}^m T_i \ge \Delta T$ to find the exact request $h_m$ whose expiration frees enough cumulative tokens:
   $$W_{\text{tpm}} = \max\left(0.5,\; (t_m + 65.0) - t_{\text{now}} + 0.35\right)$$
3. **Token-Proportional Leaky-Bucket Spacing ($W_{\text{pace}}$):**
   Even when below both ceilings, firing rapid back-to-back tool calls creates a token spike followed by a 50-second wall. The pacer enforces a smooth inter-request gap proportional to the token weight of the turn ($T_{\text{last}} = \max(E, T_k)$):
   $$G_{\text{ideal}} = \min\left(18.0,\; \max\left(\frac{60.0}{\text{hard\_rpm}} \times 0.65,\; \frac{T_{\text{last}}}{\text{hard\_tpm}} \times 52.0\right)\right)$$
   $$W_{\text{pace}} = \max\left(0.0,\; G_{\text{ideal}} - (t_{\text{now}} - t_k)\right)$$
4. **Upstream HTTP 429 Cooldown Lock ($W_{429}$):**
   If Google ever returns `HTTP 429`, `register_429_cooldown()` writes a penalty record with `unblock_ts = now + 35.0` into `rate_limit_state.json`. Any retry from `agy` is held cleanly inside `acquire_rate_slot()` for the full $W_{429}$ duration instead of hammering the upstream API.

**Total Wait Time:**
$$W_{\text{total}} = \max\left(W_{429},\; W_{\text{rpm}},\; W_{\text{tpm}},\; W_{\text{pace}}\right)$$

### Stage 4: Dual Flash-Lite Automatic Spillover (`LITE_SPILLOVER_PAIR`)
When `gemini-3.5-flash-lite` has $W_{\text{total}} > 0$ on the Free Tier, `acquire_rate_slot()` immediately evaluates its twin bucket `gemini-3.1-flash-lite-preview` (and vice versa):
- If the partner model has $W_{\text{alt}} = 0$, the proxy transparently rewrites the request path to the partner model and dispatches immediately (`0s` wait).
- If both models require a wait but $W_{\text{alt}} < W_{\text{total}}$, it selects the partner with the shorter wait.
- This combines both models into a unified **20 safe RPM (30 raw RPM) / 350K safe TPM (500K raw TPM) / 1,000 RPD** workhorse pool.

### Stage 5: Automatic 5-RPM `QUOTA GUARD` Prompt Injection
When running on the Free Tier with any model where `max_rpm <= 5` (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3-flash-preview`, `gemini-2.5-flash`), the proxy automatically injects the **Quota Guard Directive** into the turn context before JSON serialization:
> *"QUOTA GUARD (ACTIVE): You have ONLY 4 safe RPM and 20 RPD on this model. CRITICAL: NEVER chain multiple sequential tool calls or multiple subagents. Either (1) run all checks/actions in ONE single compound bash command (`cmd1 && cmd2`), OR (2) spawn AT MOST ONE subagent on flash-lite to do all legwork and return the summary to you."*

---

## 3. Model Catalog, AI Studio Quotas & Pacer Ceilings

All daily `RPD` counters in `usage.tsv` are filtered by key tier (`FREE-proxy-*` vs `PAID-proxy-*`) and reset at **Midnight Pacific Time (`00:00:00 America/Los_Angeles`)**.

| Short CLI / `!model` Alias | Upstream API Model ID | AI Studio Free Quota (Raw) | Pacer Safe Hard Cap | Paid Pricing (In / Cache / Out per 1M) | Primary Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `3.5-lite` / `3.5-flash-lite` | `gemini-3.5-flash-lite` | **15 RPM · 250K TPM · 500 RPD** | **10 RPM / 175K TPM** | $0.30 / $0.03 / $2.50 | Default TUI workhorse & minion subagent |
| `3.1-lite` / `3.1-flash-lite` | `gemini-3.1-flash-lite-preview` | **15 RPM · 250K TPM · 500 RPD** | **10 RPM / 175K TPM** | $0.25 / $0.025 / $1.50 | Auto-spillover twin for `3.5-flash-lite` |
| `2.5-lite` / `2.5-flash-lite` | `gemini-2.5-flash-lite` | **10 RPM · 250K TPM · 20 RPD** | **7 RPM / 175K TPM** | $0.10 / $0.025 / $0.40 | Secondary fast fallback |
| `3.8` / `3.8-flash` | `gemini-3.8-flash` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.75 / $0.075 / $3.75 | Primary high-reasoning planner / architect |
| `3.6` / `3.6-flash` | `gemini-3.6-flash` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.30 / $0.03 / $2.50 | Secondary reasoning & code review |
| `3.0` / `3.0-flash` | `gemini-3-flash-preview` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.30 / $0.03 / $2.50 | Reserve 20-RPD reasoning pool |
| `2.5` / `2.5-flash` | `gemini-2.5-flash` | **5 RPM · 250K TPM · 20 RPD** | **3 RPM / 175K TPM** | $0.375 / $0.0375 / $1.875 | Reserve 20-RPD reasoning pool |
| `gemma-31b` / `gemma-4-31b` | `gemma-4-31b-it` | **30 RPM · 16K TPM · 14,400 RPD** | **20 RPM / 12K TPM** | Free ($0.00) | High-volume small-context tasks |
| `gemma-26b` / `gemma-4-26b` | `gemma-4-26b-a4b-it` | **30 RPM · 16K TPM · 14,400 RPD** | **20 RPM / 12K TPM** | Free ($0.00) | High-volume small-context tasks |
| `3.1-pro` / `pro` | `gemini-3.1-pro-preview` | **0 Free (PAID KEY ONLY)** | Unthrottled (Paid) | $2.00 / $0.10 / $10.00 | Deep architectural & complex coding |
| `2.5-pro` | `gemini-2.5-pro` | **0 Free (PAID KEY ONLY)** | Unthrottled (Paid) | $1.25 / $0.125 / $10.00 | Paid Pro reasoning |
| `argon` / `4-argon` | `gemini-4-argon` | **0 Free (PAID KEY ONLY)** | Unthrottled (Paid) | $2.00 / $0.10 / $10.00 | Frontier escalation (`argon-subagent`) |

---

## 4. Generalized Installation & Zero-Trace Uninstallation

### Prerequisites
- Linux environment with `bash`, `python3` (3.10+), `git`, and the base Antigravity CLI binary installed at `~/.local/bin/agy`.

### Interactive Scoped Installation
You can clone this repository into **any temporary directory** (e.g., `~/test`). The installer will prompt you for your desired target root directory (`$TARGET_ROOT`), dynamically rewrite all internal scripts to that root, relocate the repository into `$TARGET_ROOT/projects/agy-cli_mod`, and automatically delete the temporary clone directory.

```bash
# 1. Clone into any temporary directory
mkdir -p ~/tmp_clone && cd ~/tmp_clone
git clone https://github.com/Odyssious13/agy-cli_mod.git

# 2. Run the interactive scoped installer
./agy-cli_mod/install.sh
```

**What `install.sh` does step-by-step:**
1. **Target Root Selection:** Prompts `Where should agy-api be installed and exclusively accessible from? [/mnt/storage]:` (supports `~` expansion, e.g., `~/my_workspace` or `/mnt/storage`).
2. **Dynamic Path Rewriting:** Copies `bin/*`, `workspace/*`, and `skills/*` into `$TARGET_ROOT` while rewriting all `/mnt/storage` references to `$TARGET_ROOT`.
3. **Interactive API Key Setup:** Prompts for `FREE_GEMINI_API_KEY`, `PAID_GEMINI_API_KEY`, and `ARGON_API_KEY` (you may press `Enter` to leave any key blank and fill `$TARGET_ROOT/.env` later). Sets `chmod 600` on `$TARGET_ROOT/.env`.
4. **Directory-Scoped `$PATH` Activation:** Registers `$TARGET_ROOT` in `~/.config/agy-scoped-roots.list` and installs `_agy_scoped_path_hook` into `~/.bashrc`. Your shell will automatically add `$TARGET_ROOT/bin` to `$PATH` when you `cd` inside `$TARGET_ROOT`, and strip it from `$PATH` the moment you `cd` outside.
5. **Self-Relocation & Cleanup:** Moves the git repository to `$TARGET_ROOT/projects/agy-cli_mod` and deletes `~/tmp_clone`.

Activate the hook in your current terminal and enter your workspace:
```bash
source ~/.bashrc
cd /mnt/storage   # (or your chosen $TARGET_ROOT)
```

### Zero-Trace Uninstallation (`agy-uninstall` / `uninstall.sh`)
To completely remove an installation from a target directory (including `bin/*`, `.agy-api-workspace`, `.agy-workspace`, `.claude-workspace`, `.npm-cache`, `.npm-global`, `.gemini`, `.env`, and the `~/.bashrc` registration):

```bash
# Run from inside your target root:
agy-uninstall

# Or specify a target root explicitly:
agy-uninstall ~/test2
```
The uninstaller asks for explicit `[y/N]` confirmation, steps out of `$TARGET_ROOT` if invoked from inside it, removes all mod files and hidden caches, and removes `$TARGET_ROOT` itself if the directory is now empty.

---

## 5. Complete Command Reference (Where & How to Run)

> **IMPORTANT — Directory Scope Rule:** All commands below are **strictly scoped** to `$TARGET_ROOT` (e.g., `/mnt/storage`) and its subdirectories. Running them outside `$TARGET_ROOT` will either return `command not found` (via the `$PATH` hook) or exit immediately via the hard `PWD` guard.

### A. Bash Terminal Commands (Run from `$TARGET_ROOT` or any subfolder)

| Command | Syntax & Examples | Description |
| :--- | :--- | :--- |
| **`agy-api`** | `agy-api`<br>`agy-api -m 3.5-lite -t low`<br>`agy-api -m 3.8 -t high`<br>`agy-api -m 3.5-lite -p "Reply with OK"` | Launches the API-backed CLI/TUI through `model_proxy.py`. Supports `-m` / `--model` with short aliases (`3.5-lite`, `3.1-lite`, `2.5-lite`, `3.8`, `3.6`, `3.0`, `2.5`, `3.1-pro`, `2.5-pro`, `argon`, `gemma-31b`, `gemma-26b`), `-t` / `--thinking` (`none`, `low`, `medium`, `high`), and `-p "..."` for headless prompts. |
| **`agy`** | `agy`<br>`agy -p "Summarize repo"` | Launches standard OAuth Antigravity CLI with isolated `HOME=$TARGET_ROOT/.agy-workspace`. |
| **`agy-models`** | `agy-models` | Instant (`0.02s`) Bash table displaying all Free-Tier models, Google AI Studio raw limits, Pacer hard caps, current Rolling 60s RPM/TPM usage, and Today's RPD since Midnight PT (`America/Los_Angeles`). |
| **`agy-free`** | `agy-free` | Switches `$TARGET_ROOT/.env` `GEMINI_API_KEY` to `FREE_GEMINI_API_KEY` (enables Free-Tier Rolling Pacer & Quota Guard). |
| **`agy-paid`** | `agy-paid` | Switches `$TARGET_ROOT/.env` `GEMINI_API_KEY` to `PAID_GEMINI_API_KEY` (unlocks Paid Pro/Argon models and live `$` cost HUD). |
| **`agy-key`** | `agy-key` | Prints the currently active key tier (`FREE` vs `PAID`) and the last 5 logged turns from `usage.tsv`. |
| **`agy-task`** | `agy-task <profile> <task_dir> [model]` | Runs a headless OAuth `agy` task using `PROMPT.md` in `<task_dir>` and logs execution time to `delegate.log`. |
| **`agy-uninstall`** | `agy-uninstall [target_root]` | Prompts for confirmation and cleanly removes all `agy-cli_mod` files, caches, and hooks from the target root. |

### B. Live In-Chat TUI Commands (Type inside `agy-api` chat prompt — `0ms`, `0` tokens)

When inside the interactive `agy-api` TUI, `model_proxy.py` intercepts messages starting with `!` before they ever leave your machine:

| In-Chat Command | Example | Behavior |
| :--- | :--- | :--- |
| **`!models`** | `!models` | Renders the live Markdown table of all models, AI Studio Free quotas, Pacer hard caps, Rolling 60s RPM/TPM, and Today's RPD since Midnight PT directly in the chat window. |
| **`!model <alias> [effort]`** | `!model 3.8-flash high`<br>`!model 3.5-lite 0`<br>`!model 3.0-flash low`<br>`!model reset` | Overrides the active model and optional thinking budget (`0`/`none`, `low`, `medium`, `high`) mid-conversation. `!model reset` returns control to the native `/model` TUI menu. |
| **`!effort <level>`** | `!effort 0`<br>`!effort low`<br>`!effort high` | Changes the active thinking token budget (`0` strips `thinkingConfig`; `low` = 1,024; `medium` = 8,192; `high` = 24,576). |
| **`!agy free` / `!agy paid`** | `!agy free`<br>`!agy paid` | Hot-swaps the active API key in memory AND atomically updates `$TARGET_ROOT/.env` and the bottom-left 15-byte TUI status bar without restarting `agy-api`. |

---

## 6. Multi-Agent Orchestration Workflows (Planner + Minions + Argon)

The true power of `agy-cli_mod` comes from combining **high-reasoning, low-quota models** (or external orchestrators like Claude Code) with **high-quota Free-Tier Flash-Lite minion subagents** that automatically share `rate_limit_state.json` and spill over between `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite-preview`.

### Workflow 1: High-Reasoning 5-RPM Planner (`3.8-flash`) + `3.5-flash-lite` Minion (`quota-guard`)
On the Free Tier, `gemini-3.8-flash` and `gemini-3.6-flash` have **only 5 RPM (capped at 3 safe RPM) and 20 RPD**. If `3.8-flash` reads 10 files sequentially using 10 turns, it will burn half of your daily quota in two minutes.

With **`skills/quota-guard/SKILL.md`** (auto-injected by `model_proxy.py`), `3.8-flash` acts strictly as the **Architect/Planner** and delegates all multi-step file reading, grepping, and test execution to a single `3.5-flash-lite` minion subagent (which draws from the **1,000 combined RPD / 30 combined RPM** Flash-Lite pool):

```bash
# 1. Launch agy-api on the Free Tier with Gemini 3.8 Flash (High Thinking)
agy-free
agy-api -m 3.8 -t high
```

Inside the session, when you ask `3.8-flash` to investigate a bug across your codebase, `quota-guard` instructs `3.8-flash` to run **one** bash tool call spawning a `3.5-flash-lite` minion:

```bash
# Executed automatically by the 3.8-flash planner inside a single tool turn:
agy-api -m 3.5-lite -t low -p "Inspect all Python files in workspace/, identify how rate_limit_state.json is locked, and return a concise technical summary with line numbers."
```
- **Quota Cost:** `3.8-flash` uses only **2 RPD** for the entire task (1 turn to dispatch the minion, 1 turn to synthesize the final answer), while the `3.5-flash-lite` minion handles 5–10 internal tool turns using the 1,000-RPD workhorse pool (protected by the Smooth Rolling-Window Pacer).

### Workflow 2: Delegating Bulk Tasks via `agy-api-subagent` Skill
From any orchestrator (Claude Code, OAuth `agy`, or `agy-api`), you can invoke headless `agy-api` minions in parallel or sequence to perform codebase audits, unit test generation, or log analysis at zero dollar cost:

```bash
# Fast 0-thinking Flash-Lite minion for bulk file scanning or formatting:
agy-api -m 3.5-lite -t none -p "Scan all .sh files in bin/ for bash -n syntax errors and output a markdown checklist."

# Medium-thinking Flash-Lite minion for code drafting:
agy-api -m 3.5-lite -t medium -p "Write a unit test suite for _calc_model_wait() and print the code."
```
Because all `agy-api` processes lock and read `$TARGET_ROOT/.agy-api-workspace/rate_limit_state.json`, running multiple minions automatically spaces their requests and spills over between `gemini-3.5-flash-lite` (500 RPD) and `gemini-3.1-flash-lite-preview` (500 RPD) without triggering 429 errors.

### Workflow 3: Frontier Escalation via `argon-subagent` (`call_argon.py`)
When an agent encounters a deeply complex architectural deadlock or subtle concurrency bug that requires frontier reasoning on **`gemini-4-argon`**, the `skills/argon-subagent` skill provides a dedicated, heavily guarded escalation script (`call_argon.py`):
- **Strict Manual / Last-Resort Trigger:** Configured so autonomous agents never loop on Paid Argon calls.
- **Pre-Flight Cost Confirmation & Spend Ledger:** Calculates token cost ($2.00/1M input, $0.10/1M cached, $10.00/1M output) using `ARGON_API_KEY` from `$TARGET_ROOT/.env` and records every call to `spend_ledger.csv`.

```bash
# Direct CLI invocation of the Argon specialist subagent with context files:
python3 /mnt/storage/.gemini/antigravity/skills/argon-subagent/scripts/call_argon.py \
  --prompt "Analyze model_proxy.py for any thread-safety race conditions in QuietThreadingTCPServer." \
  --file /mnt/storage/.agy-api-workspace/model_proxy.py
```

---

## 7. Repository File Structure & Maintenance

```text
agy-cli_mod/
├── AI_STUDIO_BLUEPRINT.md          # Complete architectural & UI spec for building a custom TUI/GUI
├── README.md                       # This documentation
├── .env.example                    # Sanitized template for FREE / PAID / ARGON API keys
├── .gitignore                      # Blocks .env, binaries, .tsv/.csv ledgers, and runtime logs
├── install.sh                      # Interactive, directory-scoped, self-relocating installer
├── uninstall.sh                    # Interactive zero-trace uninstaller (installed as agy-uninstall)
├── sync-from-live.sh               # Syncs live edits from $TARGET_ROOT back into this git repo
├── bin/
│   ├── _sd-env.sh                  # Workspace HOME / XDG / NPM directory isolation helper
│   ├── _sd-quiet.sh                # Headless audio/display suppressor for background agents
│   ├── agy                         # Scoped OAuth Antigravity CLI launcher
│   ├── agy-api                     # Scoped API Antigravity CLI launcher + proxy bootstrapper
│   ├── agy-models                  # Instant CLI table for AI Studio quotas & Midnight PT RPD
│   ├── agy-free                    # Shortcut to activate FREE_GEMINI_API_KEY
│   ├── agy-paid                    # Shortcut to activate PAID_GEMINI_API_KEY
│   ├── agy-key                     # Shows active key tier and last 5 usage.tsv rows
│   ├── agy-task                    # Headless task runner
│   ├── agy-uninstall               # Scoped uninstaller command
│   └── swap-key                    # Atomic .env key switcher
├── workspace/
│   ├── model_proxy.py              # Local HTTP/SSE proxy, Smooth Rolling Pacer, and ! command engine
│   ├── patch_tui_binary.py         # Byte-accurate ELF binary patcher for agy-lite-bin
│   └── record_usage.py             # Usage helper utility
└── skills/
    ├── quota-guard/SKILL.md        # 5-RPM / 20-RPD conservation protocol for 3.8/3.6 Flash
    ├── agy-api-subagent/SKILL.md   # Free-tier Flash-Lite minion delegation protocol
    └── argon-subagent/             # Frontier Gemini 4 Argon escalation skill & script
```

### Syncing Live Tweaks Back to GitHub
Whenever you modify any live script in `$TARGET_ROOT/bin` or `$TARGET_ROOT/.agy-api-workspace`, pull those changes into your repository and push in one step:

```bash
cd /mnt/storage/projects/agy-cli_mod
./sync-from-live.sh
git commit -am "Describe your update" && git push
```
