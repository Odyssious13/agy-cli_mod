#!/usr/bin/env bash
set -euo pipefail

DEFAULT_TARGET="/mnt/storage"
if [[ -n "${1:-}" ]]; then
    TARGET_ROOT="$1"
else
    read -r -p "Enter the installed root directory to uninstall from [$DEFAULT_TARGET]: " USER_IN
    TARGET_ROOT="${USER_IN:-$DEFAULT_TARGET}"
fi
TARGET_ROOT="${TARGET_ROOT%/}"

echo "================================================================"
echo "  agy-cli_mod Uninstaller"
echo "  Target Root : $TARGET_ROOT"
echo "================================================================"
echo "This will remove:"
echo "  - $TARGET_ROOT/bin/{agy,agy-api,agy-lite-bin,agy-free,agy-paid,agy-key,agy-models,agy-task,agy-uninstall,swap-key,_sd-env.sh,_sd-quiet.sh}"
echo "  - $TARGET_ROOT/.agy-api-workspace (proxy, rate state, API workspace)"
echo "  - $TARGET_ROOT/.gemini/antigravity/skills/{agy-api-subagent,argon-subagent}"
echo "  - Scoped PATH hook for $TARGET_ROOT in ~/.bashrc"
echo ""
read -r -p "Are you sure you want to uninstall agy-cli_mod from $TARGET_ROOT? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo "[ABORTED] Nothing was removed."; exit 0 ;;
esac

# 1. Remove bin wrappers and patched binary
for bf in _sd-env.sh _sd-quiet.sh agy agy-api agy-lite-bin agy-free agy-paid agy-key agy-models agy-task agy-uninstall swap-key; do
    rm -f "$TARGET_ROOT/bin/$bf"
done
rm -f "$TARGET_ROOT/swap-key.sh"
rmdir "$TARGET_ROOT/bin" 2>/dev/null || true

# 2. Remove API workspace and skills
rm -rf "$TARGET_ROOT/.agy-api-workspace"
rm -rf "$TARGET_ROOT/.gemini/antigravity/skills/agy-api-subagent"
rm -rf "$TARGET_ROOT/.gemini/antigravity/skills/argon-subagent"

# 3. Remove scoped PATH block from ~/.bashrc using Python
python3 - "$TARGET_ROOT" << 'PYCLEAN'
import re, sys
from pathlib import Path
target = sys.argv[1]
bashrc = Path.home() / '.bashrc'
if bashrc.exists():
    txt = bashrc.read_text(encoding='utf-8')
    pattern = r'\n?# >>> agy-cli_mod scoped-path \(' + re.escape(target) + r'\) >>>.*?# <<< agy-cli_mod scoped-path <<<\n?'
    new_txt = re.sub(pattern, '\n', txt, flags=re.S)
    bashrc.write_text(new_txt, encoding='utf-8')
PYCLEAN
echo "[OK] Removed scoped PATH hook from ~/.bashrc"

# 4. Optional removal of OAuth workspace, .env, and cloned repo
read -r -p "Also remove $TARGET_ROOT/.agy-workspace (OAuth history) and$TARGET_ROOT/projects/agy-cli_mod? [y/N]: " CONFIRM_EXTRA
case "$CONFIRM_EXTRA" in
    y|Y|yes|YES)
        rm -rf "$TARGET_ROOT/.agy-workspace" "$TARGET_ROOT/projects/agy-cli_mod"
        rmdir "$TARGET_ROOT/projects" 2>/dev/null || true
        echo "[OK] Removed .agy-workspace and projects/agy-cli_mod"
        ;;
    *)
        echo "[INFO] Kept $TARGET_ROOT/.agy-workspace and$TARGET_ROOT/projects/agy-cli_mod"
        ;;
esac

echo "[SUCCESS] Uninstalled agy-cli_mod from $TARGET_ROOT."
