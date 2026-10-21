#!/usr/bin/env python3
"""
Argon (API) — Cache-Maximized Single-Shot Streaming Client for /mnt/storage (SD).
Caching & Reliability Guarantees:
1. Canonical Path Resolution + Stability Ordering: Resolves all paths on /mnt/storage first, then
   orders files from OLDEST modified (st_mtime) to NEWEST modified so untouched files stay at the
   front of the KV cache even when target files are edited between calls.
2. Automatic >4,096-Token Threshold Anchor: Ensures the static prefix always exceeds Gemini 4 Argon's
   4,096-token minimum implicit caching threshold (~18,000 chars) so follow-up calls hit the 95% discount.
3. Discrete Part Boundaries: Sends static prefix parts and dynamic <task> part separately to prevent
   BPE tokenizer boundary mutations.
4. Zero Tools + Live Thought Streaming (include_thoughts=True): Prevents infinite file-reading loops
   and streams live reasoning + drop-in code patches while protecting against PROHIBITED_CONTENT loss.
"""

import argparse
import datetime
import os
import re
import sys
from pathlib import Path
from google import genai
from google.genai import types

SD_ROOT = Path("/mnt/storage")
SKILL_DIR = SD_ROOT / ".gemini/antigravity/skills/argon-subagent"
LEDGER_FILE = SKILL_DIR / "spend_ledger.csv"
SD_AGENTS_MD = SD_ROOT / "AGENTS.md"
SD_CLAUDE_MD = SD_ROOT / "CLAUDE.md"

# Minimum character floor (~4,350 tokens) to guarantee crossing Gemini's 4,096-token implicit cache threshold
MIN_CACHE_PREFIX_CHARS = 17500

SAFE_SYSTEM_INSTRUCTION = """You are Argon (API) (gemini-4-argon), a principal software engineer invoked for a SINGLE-SHOT root-cause diagnosis and code-editing pass on a local headless Linux server (/mnt/storage, referred to as SD).

CRITICAL EXECUTION & OUTPUT CONTRACT:
1. You do NOT have interactive file-reading tools in this call. All relevant repository files and logs have already been provided in <repository_context> and <task>.
2. Never ask to read more files, never stall, and never output vague architectural essays. You must deliver concrete, immediately actionable code edits in this single response.
3. Structure your response in three clear sections:
   - SECTION 1: ROOT CAUSE & REASONING (3 to 6 concise bullet points explaining what is wrong and why your fix works).
   - SECTION 2: EXACT CODE EDITS FOR /mnt/storage (For every file that needs changes, provide the exact /mnt/storage/... file path, function/line context, and unambiguous SEARCH / REPLACE blocks or drop-in code blocks so the calling agent can apply them immediately).
   - SECTION 3: HANDOFF BLOCK TO CALLER (OAUTH) formatted as:
     === MESSAGE FROM ARGON (API) ON SD TO CALLER (OAUTH) ===
     - Status: [READY_TO_APPLY | NEEDS_SPECIFIC_FILE]
     - Files to Edit on /mnt/storage: <comma-separated paths>
     - Summary of Changes: <1-2 sentences>
     - Verification Commands for Caller to Run: <exact headless/port verification commands>
     ================================================================

SERVER ENVIRONMENT SPECIFICATIONS (/mnt/storage - SD):
1. Path Isolation: All project files, virtual environments, and configs live strictly on /mnt/storage. Never reference or write to the host ~/ directory.
2. Headless Display Configuration: /mnt/storage runs as a headless server. Never launch GUI windows or browsers on physical display :0; always use offscreen virtual framebuffers (such as Xvfb) when a display context is required.
3. Null Audio Configuration: Never play audio on host hardware; always use silent/dummy audio drivers (e.g., SDL_AUDIODRIVER=dummy, null sinks, or muted flags).
4. Network Port Binding: All apps, games, web UIs, and services on /mnt/storage are accessed remotely from mobile devices or other computers over LAN or Tailscale. Always bind services to network ports (0.0.0.0 or Tailscale IP) rather than local desktop windows."""

# Deterministic static reference block used to pad small prompts past the 4,096-token implicit cache floor
DETERMINISTIC_CACHE_ANCHOR_UNIT = (
    "/* [SD_STATIC_CACHE_ANCHOR_BLOCK] Canonical Headless Linux Server (/mnt/storage) Reference Specification:\n"
    " * - Display Subsystem: Offscreen virtual framebuffer (Xvfb / headless Wayland) only; physical display :0 is prohibited.\n"
    " * - Audio Subsystem: Dummy/null audio driver (SDL_AUDIODRIVER=dummy / PULSE_SINK=null) required for all media and game loops.\n"
    " * - Network Subsystem: Bind all HTTP, WebSocket, and game server listeners to 0.0.0.0 or Tailscale interface ports.\n"
    " * - Path Isolation: Maintain all virtualenvs, node_modules, caches, and build artifacts strictly within /mnt/storage.\n"
    " * - Code Patch Standard: Emit deterministic, minimal diff blocks with exact file paths, preserving existing indentation and types.\n"
    " */\n"
)

SAFETY_SETTINGS_OFF = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.OFF,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
        threshold=types.HarmBlockThreshold.OFF,
    ),
]


def load_env_key() -> str:
    """Loads ARGON_API_KEY or PAID_GEMINI_API_KEY from environment or /mnt/storage/.env."""
    # Ensure local model_proxy.py from agy-api never intercepts direct Argon SDK calls
    os.environ.pop("GOOGLE_GEMINI_BASE_URL", None)

    free_key = os.environ.get("FREE_GEMINI_API_KEY", "").strip()
    for var in ("ARGON_API_KEY", "PAID_GEMINI_API_KEY"):
        val = os.environ.get(var, "").strip()
        if val and val != free_key:
            return val

    for env_candidate in (SD_ROOT / ".env", SKILL_DIR / ".env"):
        if env_candidate.is_file():
            env_map = {}
            for line in env_candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().removeprefix("export").strip()
                v = v.strip().strip("'").strip('"')
                if v:
                    env_map[k] = v
            free_file_key = env_map.get("FREE_GEMINI_API_KEY", "")
            for var in ("ARGON_API_KEY", "PAID_GEMINI_API_KEY"):
                if var in env_map and env_map[var] != free_file_key:
                    return env_map[var]
    return ""


def sanitize_for_classifier(text: str) -> str:
    """Strips raw credentials, private keys, and large base64/hex blobs that trigger PROHIBITED_CONTENT."""
    text = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_API_KEY]", text)
    text = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        "[REDACTED_PRIVATE_KEY]",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"data:[a-zA-Z0-9/+.-]+;base64,[A-Za-z0-9+/=]{400,}", "[REDACTED_BASE64_BLOB]", text)
    text = re.sub(r"(?<![A-Za-z0-9])[A-Fa-f0-9]{512,}(?![A-Za-z0-9])", "[REDACTED_HEX_BLOB]", text)
    return text


def build_cache_optimized_parts(
    file_paths: list[str],
    pinned_Cold_files: list[str],
    ensure_cache_floor: bool = True,
) -> tuple[list[types.Part], list[str]]:
    """
    Constructs discrete Part objects ordered by stability so KV prefix caching is maximized:
      Part 1: Immutable SD workspace rules (/mnt/storage/AGENTS.md & CLAUDE.md) + >4,096-token anchor if needed.
      Part 2..N: Resolved files sorted from OLDEST modified (st_mtime ascending) to NEWEST modified,
                 so untouched files remain cached even when the target file at the tail is edited.
    """
    # 1. Canonicalize and deduplicate all paths first
    resolved_pinned: list[Path] = []
    seen: set[Path] = set()
    for p in pinned_Cold_files:
        rp = Path(p).expanduser().resolve()
        if rp not in seen and rp.is_file():
            seen.add(rp)
            resolved_pinned.append(rp)

    resolved_dynamic: list[Path] = []
    missing_paths: list[str] = []
    for p in file_paths:
        rp = Path(p).expanduser().resolve()
        if rp in seen:
            continue
        if rp.is_file():
            seen.add(rp)
            resolved_dynamic.append(rp)
        else:
            missing_paths.append(p)

    # Sort pinned files deterministically by canonical path; sort active files by OLDEST mtime first
    # (so the file most recently edited by agy/claude is placed LAST right before <task>)
    resolved_pinned.sort(key=lambda x: str(x))
    resolved_dynamic.sort(key=lambda x: (int(x.stat().st_mtime), str(x)))
    ordered_files = resolved_pinned + resolved_dynamic

    # Build Part 1: Immutable Workspace Baseline
    baseline_blocks = ['<sd_workspace_baseline root="/mnt/storage">']
    for doc_path in (SD_AGENTS_MD, SD_CLAUDE_MD):
        if doc_path.is_file():
            cleaned = sanitize_for_classifier(doc_path.read_text(encoding="utf-8", errors="replace"))
            baseline_blocks.append(f'<workspace_rules path="{doc_path}">\n{cleaned}\n</workspace_rules>')
    baseline_blocks.append("</sd_workspace_baseline>")
    baseline_text = "\n\n".join(baseline_blocks)

    # Read all ordered files into discrete parts
    file_parts_text: list[str] = []
    ordered_labels: list[str] = []
    for rp in ordered_files:
        content = sanitize_for_classifier(rp.read_text(encoding="utf-8", errors="replace"))
        file_parts_text.append(f'<file path="{rp}">\n{content}\n</file>')
        ordered_labels.append(str(rp))

    for mp in sorted(set(missing_paths)):
        file_parts_text.append(f'<missing_file path="{mp}" />')

    # Check if total static prefix crosses the 4,096-token (~17,500 chars) implicit cache threshold
    total_static_chars = len(SAFE_SYSTEM_INSTRUCTION) + len(baseline_text) + sum(len(t) for t in file_parts_text)
    if ensure_cache_floor and total_static_chars < MIN_CACHE_PREFIX_CHARS:
        shortfall = MIN_CACHE_PREFIX_CHARS - total_static_chars
        repeats = (shortfall // len(DETERMINISTIC_CACHE_ANCHOR_UNIT)) + 2
        anchor_block = (
            "<static_cache_threshold_anchor>\n"
            + (DETERMINISTIC_CACHE_ANCHOR_UNIT * repeats)
            + "</static_cache_threshold_anchor>"
        )
        # Place the deterministic anchor inside Part 1 (before any files that might be edited!)
        baseline_text = f"{baseline_text}\n\n{anchor_block}"

    parts: list[types.Part] = [types.Part.from_text(text=baseline_text)]
    for f_txt in file_parts_text:
        parts.append(types.Part.from_text(text=f_txt))

    return parts, ordered_labels


def get_cumulative_spend() -> float:
    if not LEDGER_FILE.is_file():
        return 0.0
    total = 0.0
    for line in LEDGER_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[1:]:
        parts = line.split(",")
        if len(parts) >= 9:
            try:
                total += float(parts[-1])
            except ValueError:
                pass
    return total


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cache-maximized streaming escalation to gemini-4-argon on /mnt/storage (SD)."
    )
    parser.add_argument("--caller", default="agy", help="Spawning OAuth agent (claude or agy)")
    parser.add_argument("--thinking-level", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--max-cost", type=float, default=0.50, help="Max USD budget allowed for this call")
    parser.add_argument("--timeout-seconds", type=int, default=180, help="Hard wall-clock timeout in seconds")
    parser.add_argument("--max-output-tokens", type=int, default=65536)
    parser.add_argument(
        "--pinned-files",
        nargs="*",
        default=[],
        help="Unchanging reference files locked at the very front of the prefix cache",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        default=[],
        help="Target files on /mnt/storage (automatically sorted oldest-mtime first so edited files sit at the tail)",
    )
    parser.add_argument(
        "--no-cache-padding",
        action="store_true",
        help="Disable automatic >4,096-token floor padding on tiny prompts",
    )
    parser.add_argument(
        "--images",
        nargs="*",
        default=[],
        help="Images or screenshots to attach to the query for visual review",
    )
    parser.add_argument("--query", required=True, help="Specific bug, error trace, and edit goal")
    args = parser.parse_args()

    api_key = load_env_key()
    if not api_key:
        print(
            "ERROR: Missing ARGON_API_KEY. Export ARGON_API_KEY or add ARGON_API_KEY=... to /mnt/storage/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    static_parts, ordered_file_list = build_cache_optimized_parts(
        file_paths=args.files,
        pinned_Cold_files=args.pinned_files,
        ensure_cache_floor=not args.no_cache_padding,
    )

    clean_query = sanitize_for_classifier(args.query)
    dynamic_task_part = types.Part.from_text(
        text=(
            f'<task caller="{args.caller}" thinking_level="{args.thinking_level}" max_cost_usd="{args.max_cost:.2f}">\n'
            f"{clean_query}\n"
            f"</task>"
        )
    )

    image_parts: list[types.Part] = []
    for img_p in args.images:
        p_obj = Path(img_p).expanduser().resolve()
        if p_obj.is_file():
            mime = "image/png" if p_obj.suffix.lower() == ".png" else "image/jpeg"
            image_parts.append(types.Part.from_bytes(data=p_obj.read_bytes(), mime_type=mime))

    all_parts = static_parts + [dynamic_task_part] + image_parts
    total_chars = sum(len(p.text or "") for p in all_parts)
    est_input_tokens = (total_chars // 4) + (len(image_parts) * 1500)
    est_uncached_cost = (est_input_tokens / 1_000_000) * 2.00

    if est_uncached_cost > args.max_cost:
        print(
            f"=== ARGON (API) PRE-FLIGHT ABORT: INPUT EXCEEDS CALLER BUDGET ===\n"
            f"- Caller ({args.caller}) set --max-cost ${args.max_cost:.2f}, but worst-case uncached input "
            f"(~{est_input_tokens:,} tokens) could cost ${est_uncached_cost:.4f}.\n"
            f"- Action for {args.caller}: Narrow --files to the 2-5 relevant files or raise --max-cost.",
            file=sys.stderr,
        )
        sys.exit(2)

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=args.timeout_seconds * 1000),
    )

    config = types.GenerateContentConfig(
        system_instruction=SAFE_SYSTEM_INSTRUCTION,
        max_output_tokens=args.max_output_tokens,
        safety_settings=SAFETY_SETTINGS_OFF,
        thinking_config=types.ThinkingConfig(
            thinking_level=args.thinking_level,
            include_thoughts=True,
        ),
    )

    thought_chunks: list[str] = []
    answer_chunks: list[str] = []
    printed_thought_header = False
    printed_answer_header = False
    last_chunk = None
    block_status = "COMPLETED"

    print(
        f"[Argon (API) Connected | caller={args.caller} | thinking={args.thinking_level} | "
        f"max_cost=${args.max_cost:.2f} | prefix_order(oldest->newest)={ordered_file_list}]",
        flush=True,
    )

    try:
        for chunk in client.models.generate_content_stream(
            model="gemini-4-argon",
            contents=[types.Content(role="user", parts=all_parts)],
            config=config,
        ):
            last_chunk = chunk
            pf = getattr(chunk, "prompt_feedback", None)
            if pf and getattr(pf, "block_reason", None):
                block_status = f"LAYER_1_INPUT_BLOCK ({pf.block_reason})"
                break

            cands = getattr(chunk, "candidates", None)
            if cands:
                cand = cands[0]
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) if content else None
                if parts:
                    for part in parts:
                        txt = getattr(part, "text", None)
                        if not txt:
                            continue
                        if getattr(part, "thought", False):
                            if not printed_thought_header:
                                print("\n=== [ARGON (API) LIVE THINKING SUMMARY] ===", flush=True)
                                printed_thought_header = True
                            sys.stdout.write(txt)
                            sys.stdout.flush()
                            thought_chunks.append(txt)
                        else:
                            if not printed_answer_header:
                                print("\n\n=== [ARGON (API) CODE EDITS & SOLUTION] ===", flush=True)
                                printed_answer_header = True
                            sys.stdout.write(txt)
                            sys.stdout.flush()
                            answer_chunks.append(txt)

                fr = getattr(cand, "finish_reason", None)
                if fr and str(fr) not in (
                    "FinishReason.STOP",
                    "STOP",
                    "None",
                    "FinishReason.FINISH_REASON_UNSPECIFIED",
                ):
                    block_status = f"LAYER_2_STREAM_STOP ({fr})"
    except Exception as exc:
        block_status = f"API_ERROR_OR_TIMEOUT ({exc})"

    usage = getattr(last_chunk, "usage_metadata", None) if last_chunk else None
    prompt_tok = getattr(usage, "prompt_token_count", 0) or 0
    cached_tok = getattr(usage, "cached_content_token_count", 0) or 0
    thoughts_tok = getattr(usage, "thoughts_token_count", 0) or 0
    cand_tok = getattr(usage, "candidates_token_count", 0) or 0
    uncached_tok = max(0, prompt_tok - cached_tok)
    cache_hit_pct = (cached_tok / prompt_tok * 100.0) if prompt_tok > 0 else 0.0

    # Official Gemini 4 Argon Pricing: $2.00/1M uncached input, $0.10/1M cached input, $10.00/1M output+thinking
    cost_usd = (
        (uncached_tok / 1_000_000) * 2.00
        + (cached_tok / 1_000_000) * 0.10
        + ((thoughts_tok + cand_tok) / 1_000_000) * 10.00
    )
    saved_usd = (cached_tok / 1_000_000) * (2.00 - 0.10)

    SKILL_DIR.mkdir(parents=True, exist_ok=True)
    if not LEDGER_FILE.exists():
        LEDGER_FILE.write_text(
            "timestamp,caller,thinking_level,status,uncached_in,cached_in,thinking,output,cost_usd\n",
            encoding="utf-8",
        )
    with LEDGER_FILE.open("a", encoding="utf-8") as f:
        ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        f.write(
            f"{ts},{args.caller},{args.thinking_level},{block_status},"
            f"{uncached_tok},{cached_tok},{thoughts_tok},{cand_tok},{cost_usd:.6f}\n"
        )

    if block_status != "COMPLETED":
        print(
            f"\n\n=== [ARGON (API) DIAGNOSTIC ALERT FOR {args.caller.upper()}] ===\n"
            f"- Termination Cause: {block_status}\n"
            f"- Preserved Stream : {len(''.join(thought_chunks)):,} chars of thinking + {len(''.join(answer_chunks)):,} chars of solution saved above.\n"
            f"- Files Passed     : {ordered_file_list}\n"
            f"- Recovery Action  : "
            + (
                "Layer 1 blocked the input before generation ($0 output billed). Re-run with half the --files list to isolate which file contains a restricted string."
                if "LAYER_1" in block_status
                else "Stream ended early, but all thinking and code generated prior to termination are preserved above. Apply the partial edits above rather than blindly re-running."
            ),
            flush=True,
        )

    cum_spend = get_cumulative_spend()
    budget_flag = "WITHIN_BUDGET" if cost_usd <= args.max_cost else "EXCEEDED_CALLER_MAX_COST"

    print(
        f"\n\n=== ARGON (API) SD TELEMETRY RECEIPT FOR {args.caller.upper()} (OAUTH) ===\n"
        f"- Status & Thinking: {block_status} (thinking_level={args.thinking_level}) | {budget_flag}\n"
        f"- Input Cache Hit  : {cache_hit_pct:.1f}% ({cached_tok:,} cached @ $0.10/1M | {uncached_tok:,} uncached @ $2/1M | Saved ${saved_usd:.4f})\n"
        f"- Reasoning/Output : {thoughts_tok:,} thinking + {cand_tok:,} output tokens (@ $10/1M)\n"
        f"- Call API Cost    : ${cost_usd:.4f} USD (Caller Limit: ${args.max_cost:.2f} USD)\n"
        f"- All-Time SD Spend: ${cum_spend:.4f} USD (Ledger: {LEDGER_FILE})\n"
        f"==========================================================================",
        flush=True,
    )


if __name__ == "__main__":
    main()
