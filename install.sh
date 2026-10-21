#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORAGE_ROOT="${STORAGE_ROOT:-/mnt/storage}"
BIN_DIR="$STORAGE_ROOT/bin"
API_WS="$STORAGE_ROOT/.agy-api-workspace"
OAUTH_WS="$STORAGE_ROOT/.agy-workspace"
SHARED_SKILLS="$STORAGE_ROOT/.gemini/antigravity/skills"
ORIG_AGY="${ORIG_AGY:-$HOME/.local/bin/agy}"

echo "=== Installing agy-cli_mod (Side-by-Side OAuth agy + API agy-api) ==="

if [[ ! -x "$ORIG_AGY" ]]; then
    echo "[WARN] Base Antigravity CLI binary not found at $ORIG_AGY."
    echo "       Install Antigravity CLI first so ~/.local/bin/agy exists."
fi

mkdir -p "$BIN_DIR" "$OAUTH_WS/.gemini" "$API_WS/.gemini/antigravity-cli" "$API_WS/.gemini/skills/quota-guard" "$SHARED_SKILLS"

for f in "$REPO_ROOT/bin/"*; do
    fname="$(basename "$f")"
    cp -f "$f" "$BIN_DIR/$fname"
done
chmod 664 "$BIN_DIR/_sd-env.sh" "$BIN_DIR/_sd-quiet.sh" 2>/dev/null || true
chmod 755 "$BIN_DIR/agy" "$BIN_DIR/agy-api" "$BIN_DIR/agy-free" "$BIN_DIR/agy-paid" "$BIN_DIR/agy-key" "$BIN_DIR/agy-task" "$BIN_DIR/swap-key"
cp -f "$BIN_DIR/swap-key" "$STORAGE_ROOT/swap-key.sh"
chmod 755 "$STORAGE_ROOT/swap-key.sh"

for f in "$REPO_ROOT/workspace/"*; do
    fname="$(basename "$f")"
    cp -f "$f" "$API_WS/$fname"
    chmod 755 "$API_WS/$fname"
done

if [[ -f "$REPO_ROOT/skills/quota-guard/SKILL.md" ]]; then
    cp -f "$REPO_ROOT/skills/quota-guard/SKILL.md" "$API_WS/.gemini/skills/quota-guard/SKILL.md"
fi

for sk in agy-api-subagent argon-subagent; do
    if [[ -d "$REPO_ROOT/skills/$sk" ]]; then
        mkdir -p "$SHARED_SKILLS/$sk"
        cp -rf "$REPO_ROOT/skills/$sk/"* "$SHARED_SKILLS/$sk/"
        rm -rf "$API_WS/.gemini/skills/$sk"
        ln -s "$SHARED_SKILLS/$sk" "$API_WS/.gemini/skills/$sk"
    fi
done

printf '{\n  "modelProvider": "gemini",\n  "defaultModelId": "gemini-3.7-flash-low"\n}\n' > "$API_WS/.gemini/antigravity-cli/settings.json"

if [[ ! -f "$STORAGE_ROOT/.env" ]]; then
    cp "$REPO_ROOT/.env.example" "$STORAGE_ROOT/.env"
    chmod 600 "$STORAGE_ROOT/.env"
    echo "[INFO] Created $STORAGE_ROOT/.env from template — populate your API keys before running agy-api."
else
    echo "[OK] Preserved existing $STORAGE_ROOT/.env"
fi

if ! grep -q "$BIN_DIR" "$HOME/.bashrc" 2>/dev/null; then
    echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$HOME/.bashrc"
    echo "[OK] Added $BIN_DIR to PATH in ~/.bashrc"
fi

echo "[SUCCESS] Dual-stack installation complete! Use agy (OAuth) or agy-api (API)."
