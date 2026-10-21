#!/usr/bin/env python3
import sys
import os
import json
import glob
import re
from datetime import datetime, timezone

# Rates per 1M tokens: (input, cached_input, output) in USD
# Verified against Google AI Developer Pricing (ai.google.dev/gemini-api/docs/pricing)
# Promotional rates active through late 2026:
# - Gemini 3.8 Flash: $0.75 input, $0.075 cached, $3.75 output
# - Gemini 3.5 Flash-Lite: $0.30 input, $0.03 cached, $2.50 output
# - Gemini 3.1 Flash-Lite: $0.25 input, $0.025 cached, $1.50 output
# - Gemini 3.1 Pro / Gemini 4 Argon: $2.00 input, $0.10 cached, $10.00 output
# - Gemini 2.5 Flash: $0.375 input, $0.0375 cached, $1.875 output
PRICING = {
    "gemini-3.8-flash": (0.75, 0.075, 3.75),
    "gemini-3.5-flash-lite": (0.30, 0.03, 2.50),
    "gemini-3.1-flash-lite": (0.25, 0.025, 1.50),
    "gemini-2.5-flash": (0.375, 0.0375, 1.875),
    "gemini-3.1-pro": (2.00, 0.10, 10.00),
    "gemini-4-argon": (2.00, 0.10, 10.00),
}

def get_rates(model_name):
    m = (model_name or "").lower()
    if "argon" in m:
        return PRICING["gemini-4-argon"]
    if "pro" in m:
        return PRICING["gemini-3.1-pro"]
    if "3.1-flash-lite" in m:
        return PRICING["gemini-3.1-flash-lite"]
    if "lite" in m:
        return PRICING["gemini-3.5-flash-lite"]
    if "2.5-flash" in m:
        return PRICING["gemini-2.5-flash"]
    return PRICING["gemini-3.8-flash"]

def find_latest_transcript(brain_dir, start_time):
    transcripts = glob.glob(os.path.join(brain_dir, "*", ".system_generated", "logs", "transcript.jsonl"))
    if not transcripts:
        return None
    transcripts.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for t in transcripts:
        if os.path.getmtime(t) >= start_time - 2.0:
            return t
    return transcripts[0] if transcripts else None

def extract_model_from_log(log_path, fallback_model):
    if fallback_model:
        return fallback_model
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                matches = re.findall(r'Propagating selected model override to backend:\s*label="([^"]+)"', content)
                if matches:
                    return matches[-1]
        except Exception:
            pass
    return "gemini-3.8-flash-low"

def main():
    if len(sys.argv) < 3:
        sys.exit(0)

    start_time = float(sys.argv[1])
    cli_model = sys.argv[2]

    workspace = "/mnt/storage/.agy-api-workspace"
    brain_dir = os.path.join(workspace, ".gemini", "antigravity-cli", "brain")
    cli_log = os.path.join(workspace, ".gemini", "antigravity-cli", "cli.log")
    usage_tsv = os.path.join(workspace, "usage.tsv")

    transcript_path = find_latest_transcript(brain_dir, start_time)
    if not transcript_path or not os.path.exists(transcript_path):
        return

    parts = transcript_path.split(os.sep)
    conv_id = parts[-4] if len(parts) >= 4 else "unknown"

    model_name = extract_model_from_log(cli_log, cli_model)
    in_rate, cache_rate, out_rate = get_rates(model_name)

    total_in = 0
    total_cache = 0
    total_out = 0

    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                    total_in += d.get("input_tokens", 0)
                    total_cache += d.get("cache_read_tokens", 0)
                    total_out += d.get("output_tokens", 0)
                except Exception:
                    pass
    except Exception:
        return

    if total_in == 0 and total_cache == 0 and total_out == 0:
        return

    cost = ((total_in * in_rate) + (total_cache * cache_rate) + (total_out * out_rate)) / 1_000_000.0

    if not os.path.exists(usage_tsv):
        with open(usage_tsv, "w", encoding="utf-8") as f:
            f.write("timestamp\tconversation_id\tmodel\tinput_tokens\tcache_tokens\toutput_tokens\tcost_usd\n")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(usage_tsv, "a", encoding="utf-8") as f:
        f.write(f"{now}\t{conv_id}\t{model_name}\t{total_in}\t{total_cache}\t{total_out}\t{cost:.5f}\n")

    print(f"[agy-api] Usage: model={model_name} | in={total_in} cache={total_cache} out={total_out} | cost=${cost:.5f} | logged to {usage_tsv}", file=sys.stderr)

if __name__ == "__main__":
    main()
