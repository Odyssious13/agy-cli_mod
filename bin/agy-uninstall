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
echo "This will completely remove all agy-cli_mod files, workspaces, caches, and .env in $TARGET_ROOT."
read -r -p "Are you sure you want to uninstall everything from $TARGET_ROOT? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo "[ABORTED] Nothing was removed."; exit 0 ;;
esac

# Step out of TARGET_ROOT if the script was invoked from inside it
case "$PWD/" in
    "$TARGET_ROOT/"*) cd "$(dirname "$TARGET_ROOT")" 2>/dev/null || cd "$HOME" ;;
esac

# 1. Remove bin wrappers and patched binary
for bf in _sd-env.sh _sd-quiet.sh agy agy-api agy-lite-bin agy-free agy-paid agy-key agy-models agy-task agy-uninstall swap-key; do
    rm -f "$TARGET_ROOT/bin/$bf"
done
rm -f "$TARGET_ROOT/swap-key.sh"
rmdir "$TARGET_ROOT/bin" 2>/dev/null || true

# 2. Remove all workspaces, npm caches, skills, .env, and relocated repo
rm -rf "$TARGET_ROOT/.agy-api-workspace"
rm -rf "$TARGET_ROOT/.agy-workspace"
rm -rf "$TARGET_ROOT/.claude-workspace"
rm -rf "$TARGET_ROOT/.npm-cache"
rm -rf "$TARGET_ROOT/.npm-global"
rm -rf "$TARGET_ROOT/.gemini/antigravity/skills/agy-api-subagent"
rm -rf "$TARGET_ROOT/.gemini/antigravity/skills/argon-subagent"
rmdir "$TARGET_ROOT/.gemini/antigravity/skills" "$TARGET_ROOT/.gemini/antigravity" "$TARGET_ROOT/.gemini" 2>/dev/null || true
rm -f "$TARGET_ROOT/.env"
rm -rf "$TARGET_ROOT/projects/agy-cli_mod"
rmdir "$TARGET_ROOT/projects" 2>/dev/null || true

# 3. Remove TARGET_ROOT itself if it is now completely empty (never deletes non-empty drives like /mnt/storage)
rmdir "$TARGET_ROOT" 2>/dev/null || true

# 4. Unregister from ~/.config/agy-scoped-roots.list and clean PATH
ROOTS_FILE="$HOME/.config/agy-scoped-roots.list"
if [[ -f "$ROOTS_FILE" ]]; then
    grep -vxF "$TARGET_ROOT" "$ROOTS_FILE" > "${ROOTS_FILE}.tmp" || true
    mv "${ROOTS_FILE}.tmp" "$ROOTS_FILE"
fi
export PATH="$(echo ":$PATH:" | sed "s@:$TARGET_ROOT/bin:@:@g; s@^:@@; s@:\$@@")"

echo "[SUCCESS] Completely uninstalled agy-cli_mod and cleaned all caches from $TARGET_ROOT."
