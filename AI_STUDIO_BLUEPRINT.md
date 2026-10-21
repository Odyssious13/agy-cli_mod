# AI Studio Blueprint: Custom TUI & Agent Orchestrator (`agy-cli_mod`)

## 1. Executive Summary & Architectural Decision
We are building a custom **Terminal User Interface (TUI)** and **Multi-Model Agent Orchestrator** on Linux (`/mnt/storage`) that wraps or replaces the Antigravity CLI (`agy`) TUI while preserving 100% compatibility with our dual-stack environment (`agy` OAuth + `agy-api` Google AI Studio API proxy).

### Why a Custom TUI (Python `Textual` / Go `Bubble Tea`) Instead of a Full Terminal Emulator?
- We run inside **Ghostty** on Ubuntu Cinnamon (`optiplex-3060`), which already provides GPU-accelerated font rendering, PTY handling, and clipboard integration.
- Building a custom **TUI application** (using Python `Textual` or `Rich` + `prompt_toolkit`) gives us full mouse support, clickable model/effort/key-tier selectors, live rolling-window RPM/TPM/RPD quota gauges, collapsible tool-call accordions, and real-time `$` spend tracking without reinventing VT100 terminal emulation.

---

## 2. Repository File Map & Live Runtime Paths

| Repo Path | Installed Path on `/mnt/storage` | Role |
| :--- | :--- | :--- |
| `bin/agy-api` | `/mnt/storage/bin/agy-api` | Main API CLI/TUI wrapper; loads `/mnt/storage/.env`, starts `model_proxy.py`, patches `agy-lite-bin`, exports `GOOGLE_GEMINI_BASE_URL` |
| `bin/agy` | `/mnt/storage/bin/agy` | Standard OAuth CLI wrapper (`HOME=/mnt/storage/.agy-workspace`) |
| `bin/swap-key` | `/mnt/storage/bin/swap-key` (`agy-free`, `agy-paid`, `agy-key`) | Shell utilities to toggle `GEMINI_API_KEY` between `FREE_GEMINI_API_KEY` and `PAID_GEMINI_API_KEY` |
| `workspace/model_proxy.py` | `/mnt/storage/.agy-api-workspace/model_proxy.py` | Local HTTP/SSE proxy with Smooth Rolling-Window Pacer, 3.5<->3.1 Flash-Lite spillover, Midnight PT RPD tracking, and `!` chat commands |
| `workspace/patch_tui_binary.py` | `/mnt/storage/.agy-api-workspace/patch_tui_binary.py` | Byte-accurate ELF binary patcher for `/mnt/storage/bin/agy-lite-bin` (15-byte bottom-left status bar HUD + model slot labels) |
| `skills/quota-guard/SKILL.md` | `/mnt/storage/.agy-api-workspace/.gemini/skills/quota-guard/SKILL.md` | Mandatory 5-RPM / 20-RPD conservation skill for `Gemini 3.8 Flash` & `3.6 Flash` |
| `skills/agy-api-subagent/SKILL.md` | `/mnt/storage/.gemini/antigravity/skills/agy-api-subagent/SKILL.md` | Subagent delegation skill |
| `skills/argon-subagent/` | `/mnt/storage/.gemini/antigravity/skills/argon-subagent/` | Argon frontier escalation skill & script |

---

## 3. Complete Model Catalog, Safe Pacing Caps (Free Tier), & Paid Pricing

All Free-Tier RPD quotas reset at **Midnight Pacific Time (`America/Los_Angeles`)**. RPM and TPM operate on a **65-second rolling window** with hard safety caps below Google's raw limits and automatic token-proportional spacing:

| `!model` Alias | Upstream API Model ID | Free Hard Cap (Raw Limit) | Daily Free RPD (Midnight PT) | Paid Pricing (In / Cache / Out per 1M) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `3.5-flash-lite` | `gemini-3.5-flash-lite` | **12 RPM / 190K TPM** (15 RPM / 250K) | **500 RPD** | $0.30 / $0.03 / $2.50 | Default workhorse; auto-spills to `3.1-flash-lite` |
| `3.1-flash-lite` | `gemini-3.1-flash-lite-preview` | **12 RPM / 190K TPM** (15 RPM / 250K) | **500 RPD** | $0.25 / $0.025 / $1.50 | Auto-spillover partner (Combined: **24 safe RPM / 380K safe TPM / 1,000 RPD**) |
| `2.5-flash-lite` | `gemini-2.5-flash-lite` | **8 RPM / 190K TPM** (10 RPM / 250K) | **20 RPD** | $0.10 / $0.025 / $0.40 | Secondary lightweight model |
| `3.8-flash` | `gemini-3.8-flash` | **4 RPM / 190K TPM** (5 RPM / 250K) | **20 RPD** | $0.75 / $0.075 / $3.75 | Primary high-reasoning planner (uses `quota-guard`) |
| `3.6-flash` | `gemini-3.6-flash` | **4 RPM / 190K TPM** (5 RPM / 250K) | **20 RPD** | $0.30 / $0.03 / $2.50 | Secondary reasoning model (uses `quota-guard`) |
| `3.0-flash` | `gemini-3-flash-preview` | **4 RPM / 190K TPM** (5 RPM / 250K) | **20 RPD** | $0.30 / $0.03 / $2.50 | Accessible via `!model 3.0-flash` |
| `2.5-flash` | `gemini-2.5-flash` | **4 RPM / 190K TPM** (5 RPM / 250K) | **20 RPD** | $0.375 / $0.0375 / $1.875 | Accessible via `!model 2.5-flash` |
| `gemma-4-31b` | `gemma-4-31b-it` | **24 RPM / 12K TPM** (30 RPM / 15K) | **14,400 RPD** | Free / $0.00 | High-RPD lightweight model |
| `gemma-4-26b` | `gemma-4-26b-a4b-it` | **24 RPM / 12K TPM** (30 RPM / 15K) | **14,400 RPD** | Free / $0.00 | High-RPD lightweight model |
| `3.1-pro` | `gemini-3.1-pro-preview` | **0 Free (Paid Only)** | **0 Free** | $2.00 / $0.10 / $10.00 | Requires `!agy paid` |
| `2.5-pro` | `gemini-2.5-pro` | **0 Free (Paid Only)** | **0 Free** | $1.25 / $0.125 / $10.00 | Requires `!agy paid` |
| `argon` | `gemini-4-argon` | **0 Free (Paid Only)** | **0 Free** | $2.00 / $0.10 / $10.00 | Requires `!agy paid` |

---

## 4. Custom TUI Specification for Google AI Studio

### A. Core Architecture (Python `Textual` TUI)
Build a standalone Python `Textual` application (`tui_app.py`) that integrates directly with `/mnt/storage/.agy-api-workspace/model_proxy.py` and shared state files:
1. **Shared State Files**:
   - `/mnt/storage/.env`: Contains `FREE_GEMINI_API_KEY`, `PAID_GEMINI_API_KEY`, `ARGON_API_KEY`, and active `GEMINI_API_KEY`.
   - `/mnt/storage/.agy-api-workspace/rate_limit_state.json`: `fcntl.flock`-locked rolling 65-second window array `[{"id": "...", "ts": 1760990000.0, "tokens": 18420, "model": "gemini-3.5-flash-lite"}]`.
   - `/mnt/storage/.agy-api-workspace/usage.tsv`: Append-only TSV (`timestamp_utc`, `session_id`, `model`, `uncached_in`, `cached_in`, `out_tokens`, `cost_usd`).

### B. UI Layout & Widgets
1. **Top Header Bar**:
   - Displays active Working Directory (`$PWD`), Git branch/dirty state, Key Tier Badge (`[FREE TIER]` in green or `[PAID TIER]` in gold), and Midnight PT RPD reset countdown.
2. **Main Chat & Tool Viewport**:
   - Renders streaming Markdown responses, collapsible `Thought` blocks (showing thinking budget `0` / `1k` / `8k` / `24k` and token count), and collapsible Tool Call / Subagent cards (`run_command`, `read_file`, `edit_file`, `invoke_subagent`).
   - When the Smooth Rolling-Window Pacer spaces out a request or waits for cumulative tokens to expire, renders a non-blocking live progress bar (`Pacing request: 6.4s remaining — 168k/190k TPM used`).
3. **Bottom HUD Status Bar**:
   - **Left**: Live rolling 65s gauges (`RPM: 4/12 | TPM: 64k/190k | Today RPD: 42/500 | Spillover: Ready`) in Free mode, or (`Session: $0.0184 | Today: $0.1420 | Cache Hit: 88%`) in Paid mode.
   - **Right**: Clickable Model Selector (`gemini-3.5-flash-lite`, `gemini-3.8-flash`, etc.) and Thinking Effort Selector (`0-think`, `low`, `medium`, `high`).
4. **Built-in Slash & Bang Commands (`0ms` local execution)**:
   - `!agy free` / `!agy paid`, `!models`, `!model <alias> [effort]`, `!effort <level>`.
