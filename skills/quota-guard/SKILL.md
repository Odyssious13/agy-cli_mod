---
name: quota-guard
description: Mandatory RPM/RPD quota conservation protocol for agy-api when running on 5 RPM / 20 RPD models (Gemini 3.8 Flash, 3.6 Flash, 3.0 Flash, 2.5 Flash) or delegating multi-step investigation/execution tasks to Gemini 3.5 Flash-Lite (15 RPM / 500 RPD).
---

# agy-api Quota Conservation & Subagent Delegation Protocol

When running inside `agy-api` on low-quota models (`gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3-flash-preview`, `gemini-2.5-flash` — **5 RPM / 20 RPD on Free Tier**), every tool call you make consumes 1 separate HTTP request from the 20 RPD daily bucket.

## Mandatory Execution Rules

1. **NEVER Chain Sequential Tool Calls Yourself on 5 RPM / 20 RPD Models:**
   - Target **2 API requests total per user turn**: Request #1 (one tool call) -> Request #2 (final response).
   - Never run `ls`, then `cat`, then `grep`, then `systemctl` across separate turns.

2. **Rule A — Mechanical Multi-Command Tasks (Use 1 Compound Bash Call):**
   - If you already know the exact shell commands to run (e.g., checking status, restarting a service, tailing logs, and verifying endpoints), combine them into **one single bash tool call** joined with `&&` or `;`:
     ```bash
     systemctl --user restart kk-companion && sleep 2 && systemctl --user status kk-companion --no-pager && curl -s http://127.0.0.1:8080/api/status
     ```

3. **Rule B — Open-Ended Investigation, Log Hunting, or Multi-File Edits (Spawn ONE `3.5-flash-lite` Subagent):**
   - If a task requires searching files, reading multiple logs, diagnosing errors, or making iterative edits, delegate the entire investigation/action loop to **ONE** `agy-api` subagent running on `gemini-3.5-flash-lite` (which has its own separate **15 RPM / 500 RPD** quota bucket):
     ```bash
     agy-api -m 3.5-flash-lite -p "Working in $(pwd): <complete instructions of everything to inspect, fix, restart, and verify>. Return a concise summary of findings and actions taken."
     ```
   - **CRITICAL:** Spawn **ONE** comprehensive `3.5-flash-lite` subagent per turn—do NOT spawn multiple subagents sequentially or in parallel (`&`), as parallel subagents share the 240K TPM input window.
