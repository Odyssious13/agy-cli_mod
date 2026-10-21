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
    echo "       Install Antigravity CLI first so ~/.local/bin/agy exists."
fi

mkdir -p "$BIN_DIR" "$OAUTH_WS/.gemini" "$API_WS/.gemini/antigravity-cli"
mkdir -p "$API_WS/.gemini/skills/quota-guard" "$SHARED_SKILLS" "$TARGET_ROOT/projects"

# 1. Copy bin scripts and dynamically rewrite /mnt/storage -> $TARGET_ROOT
for f in "$CLONE_DIR/bin/"*; do
    fname="$(basename "$f")"
    sed "s@/mnt/storage@$TARGET_ROOT@g" "$f" > "$BIN_DIR/$fname"
done
sed "s@/mnt/storage@$TARGET_ROOT@g" "$CLONE_DIR/uninstall.sh" > "$BIN_DIR/agy-uninstall"
chmod 664 "$BIN_DIR/_sd-env.sh" "$BIN_DIR/_sd-quiet.sh" 2>/dev/null || true
chmod 755 "$BIN_DIR/agy" "$BIN_DIR/agy-api" "$BIN_DIR/agy-free" "$BIN_DIR/agy-paid" "$BIN_DIR/agy-key" "$BIN_DIR/agy-models" "$BIN_DIR/agy-task" "$BIN_DIR/agy-uninstall" "$BIN_DIR/swap-key"
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

# 4. Seed $TARGET_ROOT/.env if not present
if [[ ! -f "$TARGET_ROOT/.env" ]]; then
    sed "s@/mnt/storage@$TARGET_ROOT@g" "$CLONE_DIR/.env.example" > "$TARGET_ROOT/.env"
    chmod 600 "$TARGET_ROOT/.env"
    echo "[INFO] Created $TARGET_ROOT/.env — add your API keys there."
else
    echo "[OK] Preserved existing $TARGET_ROOT/.env"
fi

# 5. Install directory-scoped PATH hook in ~/.bashrc
HOOK_MARKER="# >>> agy-cli_mod scoped-path ($TARGET_ROOT) >>>"
if ! grep -qF "$HOOK_MARKER" "$HOME/.bashrc" 2>/dev/null; then
    cat >> "$HOME/.bashrc" << EOF
$HOOK_MARKER
_agy_scoped_path_hook() {
  case "\$PWD/" in
    "$TARGET_ROOT/"*)
      case ":\$PATH:" in *":$BIN_DIR:"*) ;; *) export PATH="$BIN_DIR:\$PATH" ;; esac
      ;;
    *)
      export PATH="\$(echo ":\$PATH:" | sed "s@:$BIN_DIR:@:@g; s@^:@@; s@:\$@@")"
      ;;
  esac
}
case "\${PROMPT_COMMAND:-}" in *_agy_scoped_path_hook*) ;; *) PROMPT_COMMAND="_agy_scoped_path_hook\${PROMPT_COMMAND:+;\$PROMPT_COMMAND}" ;; esac
# <<< agy-cli_mod scoped-path <<<
EOF
    echo "[OK] Installed directory-scoped PATH hook in ~/.bashrc (active ONLY inside $TARGET_ROOT)"
fi

# 6. Relocate git repo into $FINAL_REPO_DIR and remove temporary clone dir
if [[ "$CLONE_DIR" != "$FINAL_REPO_DIR" ]]; then
    rm -rf "$FINAL_REPO_DIR"
    mkdir -p "$(dirname "$FINAL_REPO_DIR")"
    cp -a "$CLONE_DIR" "$FINAL_REPO_DIR"
    PARENT_DIR="$(dirname "$CLONE_DIR")"
    rm -rf "$CLONE_DIR"
    rmdir "$PARENT_DIR" 2>/dev/null || true
    echo "[OK] Moved repo to $FINAL_REPO_DIR and cleaned up temporary clone at$CLONE_DIR"
fi

echo "[SUCCESS] Scoped installation complete!"
echo "  - Accessible ONLY when inside directory: $TARGET_ROOT"
echo "  - Commands: agy, agy-api, agy-models, agy-free, agy-paid, agy-key, agy-uninstall"
