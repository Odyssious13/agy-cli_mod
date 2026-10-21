#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for bf in _sd-env.sh _sd-quiet.sh agy agy-api agy-free agy-paid agy-key agy-models agy-task agy-uninstall swap-key; do
    [[ -f "/mnt/storage/bin/$bf" ]] && cp -f "/mnt/storage/bin/$bf" "$REPO_ROOT/bin/$bf"
done

for wf in model_proxy.py patch_tui_binary.py record_usage.py; do
    [[ -f "/mnt/storage/.agy-api-workspace/$wf" ]] && cp -f "/mnt/storage/.agy-api-workspace/$wf" "$REPO_ROOT/workspace/$wf"
done

if [[ -f "/mnt/storage/.agy-api-workspace/.gemini/skills/quota-guard/SKILL.md" ]]; then
    cp -f "/mnt/storage/.agy-api-workspace/.gemini/skills/quota-guard/SKILL.md" "$REPO_ROOT/skills/quota-guard/SKILL.md"
fi

for sk in agy-api-subagent argon-subagent; do
    if [[ -d "/mnt/storage/.gemini/antigravity/skills/$sk" ]]; then
        cp -rf "/mnt/storage/.gemini/antigravity/skills/$sk/"* "$REPO_ROOT/skills/$sk/"
    fi
done

rm -rf "$REPO_ROOT/skills/argon-subagent/spend_ledger.csv" "$REPO_ROOT/skills/argon-subagent/scripts/__pycache__"
echo "[OK] Synced live /mnt/storage scripts & skills into $REPO_ROOT"
git -C "$REPO_ROOT" status -s
