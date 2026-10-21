#!/usr/bin/env bash
set -euo pipefail

DEFAULT_TARGET="/mnt/storage"
if [[ -n "${1:-}" ]]; then
    TARGET_ROOT="$1"
else
    read -r -p "Enter the installed root directory to uninstall from [$DEFAULT_TARGET]: " USER_IN
    TARGET_ROOT="${USER_IN:-$DEFAULT_TARGET}"
fi
TARGET_ROOT="${TARGET_ROOT/#\~/$HOME}"
TARGET_ROOT="${TARGET_ROOT%/}"

echo "================================================================"
echo "  agy-cli_mod Uninstaller"
echo "  Target Root : $TARGET_ROOT"
echo "================================================================"
read -r -p "Are you sure you want to uninstall agy-cli_mod from $TARGET_ROOT? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo "[ABORTED] Nothing was removed."; exit 0 ;;
esac

for bf in _sd-env.sh _sd-quiet.sh agy agy-api agy-lite-bin agy-free agy-paid agy-key agy-models agy-task agy-uninstall swap-key; do
    rm -f "$TARGET_ROOT/bin/$bf"
done
rm -f "$TARGET_ROOT/swap-key.sh"
rmdir "$TARGET_ROOT/bin" 2>/dev/null || true
rm -rf "$TARGET_ROOT/.agy-api-workspace"
rm -rf "$TARGET_ROOT/.gemini/antigravity/skills/agy-api-subagent"
rm -rf "$TARGET_ROOT/.gemini/antigravity/skills/argon-subagent"
rmdir "$TARGET_ROOT/.gemini/antigravity/skills" "$TARGET_ROOT/.gemini/antigravity" "$TARGET_ROOT/.gemini" 2>/dev/null || true

ROOTS_FILE="$HOME/.config/agy-scoped-roots.list"
if [[ -f "$ROOTS_FILE" ]]; then
    grep -vxF "$TARGET_ROOT" "$ROOTS_FILE" > "${ROOTS_FILE}.tmp" || true
    mv "${ROOTS_FILE}.tmp" "$ROOTS_FILE"
fi
export PATH="$(echo ":$PATH:" | sed "s@:$TARGET_ROOT/bin:@:@g; s@^:@@; s@:\$@@")"

read -r -p "Also remove $TARGET_ROOT/.agy-workspace, $TARGET_ROOT/.env, and $TARGET_ROOT/projects/agy-cli_mod? [y/N]: " CONFIRM_EXTRA
case "$CONFIRM_EXTRA" in
    y|Y|yes|YES)
        rm -rf "$TARGET_ROOT/.agy-workspace" "$TARGET_ROOT/.claude-workspace" "$TARGET_ROOT/.env" "$TARGET_ROOT/projects/agy-cli_mod"
        rmdir "$TARGET_ROOT/projects" "$TARGET_ROOT" 2>/dev/null || true
        echo "[OK] Removed all workspaces, .env, and empty target directory."
        ;;
    *)
        echo "[INFO] Kept .agy-workspace, .env, and projects/agy-cli_mod"
        ;;
esac
echo "[SUCCESS] Uninstalled agy-cli_mod from $TARGET_ROOT."
