#!/usr/bin/env bash
set -euo pipefail

CLONE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIG_AGY="${ORIG_AGY:-$HOME/.local/bin/agy}"

echo "=== agy-cli_mod Interactive Scoped Installer ==="
DEFAULT_TARGET="/mnt/storage"
if [[ -n "${1:-}" ]]; then
    TARGET_ROOT="$1"
else
    read -r -p "Where should agy-api be installed and exclusively accessible from? [$DEFAULT_TARGET]: " USER_IN
    TARGET_ROOT="${USER_IN:-$DEFAULT_TARGET}"
fi

TARGET_ROOT="${TARGET_ROOT/#\~/$HOME}"
TARGET_ROOT="${TARGET_ROOT%/}"
mkdir -p "$TARGET_ROOT"
TARGET_ROOT="$(cd "$TARGET_ROOT" && pwd)"

BIN_DIR="$TARGET_ROOT/bin"
API_WS="$TARGET_ROOT/.agy-api-workspace"
OAUTH_WS="$TARGET_ROOT/.agy-workspace"
SHARED_SKILLS="$TARGET_ROOT/.gemini/antigravity/skills"
FINAL_REPO_DIR="$TARGET_ROOT/projects/agy-cli_mod"

echo "[INFO] Installing scoped environment into: $TARGET_ROOT"

if [[ ! -x "$ORIG_AGY" ]]; then
    echo "[WARN] Base Antigravity CLI binary not found at $ORIG_AGY."
fi

mkdir -p "$BIN_DIR" "$OAUTH_WS/.gemini" "$API_WS/.gemini/antigravity-cli"
mkdir -p "$API_WS/.gemini/skills/quota-guard" "$SHARED_SKILLS" "$TARGET_ROOT/projects"

# 1. Copy bin scripts and rewrite /mnt/storage -> $TARGET_ROOT
for f in "$CLONE_DIR/bin/"*; do
    fname="$(basename "$f")"
    rm -f "$BIN_DIR/$fname"
    rm -f "$BIN_DIR/$fname"
    sed "s@/mnt/storage@$TARGET_ROOT@g" "$f" > "$BIN_DIR/$fname"
done
sed "s@/mnt/storage@$TARGET_ROOT@g" "$CLONE_DIR/uninstall.sh" > "$BIN_DIR/agy-uninstall"
chmod 664 "$BIN_DIR/_sd-env.sh" "$BIN_DIR/_sd-quiet.sh" 2>/dev/null || true
chmod 755 "$BIN_DIR/agy" "$BIN_DIR/agy-api" "$BIN_DIR/agy-free" "$BIN_DIR/agy-paid" "$BIN_DIR/agy-key" "$BIN_DIR/agy-models" "$BIN_DIR/agy-task" "$BIN_DIR/agy-uninstall" "$BIN_DIR/swap-key"
rm -f "$TARGET_ROOT/swap-key.sh"
rm -f "$TARGET_ROOT/swap-key.sh"
cp -f "$BIN_DIR/swap-key" "$TARGET_ROOT/swap-key.sh"
chmod 755 "$TARGET_ROOT/swap-key.sh"

# 2. Copy workspace scripts and rewrite /mnt/storage -> $TARGET_ROOT
for f in "$CLONE_DIR/workspace/"*; do
    fname="$(basename "$f")"
    sed "s@/mnt/storage@$TARGET_ROOT@g" "$f" > "$API_WS/$fname"
    chmod 755 "$API_WS/$fname"
done

# 3. Install skills and rewrite paths
if [[ -f "$CLONE_DIR/skills/quota-guard/SKILL.md" ]]; then
    sed "s@/mnt/storage@$TARGET_ROOT@g" "$CLONE_DIR/skills/quota-guard/SKILL.md" > "$API_WS/.gemini/skills/quota-guard/SKILL.md"
fi

for sk in agy-api-subagent argon-subagent; do
    if [[ -d "$CLONE_DIR/skills/$sk" ]]; then
        mkdir -p "$SHARED_SKILLS/$sk"
        cp -rf "$CLONE_DIR/skills/$sk/"* "$SHARED_SKILLS/$sk/"
        find "$SHARED_SKILLS/$sk" -type f -exec sed -i "s@/mnt/storage@$TARGET_ROOT@g" {} +
        rm -rf "$API_WS/.gemini/skills/$sk"
        ln -s "$SHARED_SKILLS/$sk" "$API_WS/.gemini/skills/$sk"
    fi
done

printf '{\n  "modelProvider": "gemini",\n  "defaultModelId": "gemini-3.7-flash-low"\n}\n' > "$API_WS/.gemini/antigravity-cli/settings.json"

# 4. Interactive API key setup for $TARGET_ROOT/.env (press Enter to leave blank)
if [[ ! -f "$TARGET_ROOT/.env" ]]; then
    echo ""
    echo "--- API Key Setup for $TARGET_ROOT/.env (Press Enter to skip and fill later) ---"
    read -r -p "  FREE_GEMINI_API_KEY : " IN_FREE || true
    read -r -p "  PAID_GEMINI_API_KEY : " IN_PAID || true
    read -r -p "  ARGON_API_KEY       : " IN_ARGON || true
    ACTIVE_INIT="${IN_FREE:-${IN_PAID:-}}"
    cat > "$TARGET_ROOT/.env" << ENVEOF
# API keys for $TARGET_ROOT
FREE_GEMINI_API_KEY=${IN_FREE}
PAID_GEMINI_API_KEY=${IN_PAID}
ARGON_API_KEY=${IN_ARGON}
GEMINI_API_KEY=${ACTIVE_INIT}
ENVEOF
    chmod 600 "$TARGET_ROOT/.env"
    echo "[OK] Created $TARGET_ROOT/.env"
else
    echo "[OK] Preserved existing $TARGET_ROOT/.env"
fi

# 5. Register $TARGET_ROOT in ~/.config/agy-scoped-roots.list and install unified PATH hook
ROOTS_FILE="$HOME/.config/agy-scoped-roots.list"
mkdir -p "$HOME/.config"
touch "$ROOTS_FILE"
if ! grep -qxF "$TARGET_ROOT" "$ROOTS_FILE" 2>/dev/null; then
    echo "$TARGET_ROOT" >> "$ROOTS_FILE"
fi

# Remove old static /mnt/storage/bin exports or old single-root hooks in ~/.bashrc
python3 - << 'PYBASH'
import re
from pathlib import Path
bashrc = Path.home() / '.bashrc'
if bashrc.exists():
    txt = bashrc.read_text(encoding='utf-8')
    txt = re.sub(r'\n?# >>> agy-cli_mod scoped-path.*?# <<< agy-cli_mod scoped-path <<<\n?', '\n', txt, flags=re.S)
    txt = re.sub(r'^.*export PATH="/mnt/storage/bin:\$PATH".*\n?', '', txt, flags=re.M)
    bashrc.write_text(txt, encoding='utf-8')
PYBASH

HOOK_MARKER="# >>> agy-cli_mod unified-scoped-path >>>"
if ! grep -qF "$HOOK_MARKER" "$HOME/.bashrc" 2>/dev/null; then
    cat >> "$HOME/.bashrc" << 'EOF'
# >>> agy-cli_mod unified-scoped-path >>>
_agy_scoped_path_hook() {
  local roots_file="$HOME/.config/agy-scoped-roots.list"
  [[ -f "$roots_file" ]] || return 0
  local r b
  while IFS= read -r r; do
    [[ -n "$r" ]] || continue
    b="$r/bin"
    if [[ ":$PATH:" == *":$b:"* ]]; then
      PATH="$(echo ":$PATH:" | sed "s@:$b:@:@g; s@^:@@; s@:\$@@")"
    fi
  done < "$roots_file"
  while IFS= read -r r; do
    [[ -n "$r" ]] || continue
    b="$r/bin"
    case "$PWD/" in
      "$r/"*) PATH="$b:$PATH" ;;
    esac
  done < "$roots_file"
  export PATH
}
case "${PROMPT_COMMAND:-}" in *_agy_scoped_path_hook*) ;; *) PROMPT_COMMAND="_agy_scoped_path_hook${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;; esac
_agy_scoped_path_hook
# <<< agy-cli_mod unified-scoped-path <<<
EOF
    echo "[OK] Installed unified directory-scoped PATH hook in ~/.bashrc"
fi

# 6. Relocate git repo into $FINAL_REPO_DIR and remove temporary clone dir
if [[ "$CLONE_DIR" != "$FINAL_REPO_DIR" ]]; then
    rm -rf "$FINAL_REPO_DIR"
    mkdir -p "$(dirname "$FINAL_REPO_DIR")"
    cp -a "$CLONE_DIR" "$FINAL_REPO_DIR"
    PARENT_DIR="$(dirname "$CLONE_DIR")"
    cd "$TARGET_ROOT"
    rm -rf "$CLONE_DIR"
    rmdir "$PARENT_DIR" 2>/dev/null || true
    echo "[OK] Moved repo to $FINAL_REPO_DIR and cleaned up temporary clone at $CLONE_DIR"
fi

echo "[SUCCESS] Scoped installation complete for: $TARGET_ROOT"
echo "  Next step: source ~/.bashrc && cd $TARGET_ROOT"
