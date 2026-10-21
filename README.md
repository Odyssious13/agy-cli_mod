# agy-cli_mod

Side-by-side OAuth (agy) + Google AI Studio API (agy-api) mod stack for Antigravity CLI on /mnt/storage.

## Features
- **Isolated Dual Stack**: Standard OAuth `agy` uses `/mnt/storage/.agy-workspace`. `agy-api` uses `/mnt/storage/.agy-api-workspace` and `/mnt/storage/bin/agy-lite-bin`.
- **Live Bottom-Left Status Bar HUD**: Replaces `? for shortcuts` with `FREE 1/15R 8kT` or `PAID $0.0046 1R` in-place without duplicating model/effort.
- **480K TPM / 30 RPM Auto-Spillover**: Automatically load-balances Free-Tier Flash-Lite requests between `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite-preview`.
- **In-Chat Live Commands**:
  - `!agy free` / `!agy paid` (or `!free` / `!paid`): Hot-swaps API keys and updates `/mnt/storage/.env` and the status bar on the spot.
  - `!models`: Lists extra usable models not shown in `/model` (`3.1-flash-lite`, `2.5-flash-lite`, `3.0-flash`, `2.5-flash`, `2.5-pro`, `gemma-4-26b`, `gemma-4-31b`).
  - `!model <alias> [0|low|medium|high]`: Switches active model and thinking effort mid-conversation.
  - `!effort <0|low|medium|high>`: Changes thinking budget live.
- **5-RPM Quota Guard (`skills/quota-guard/SKILL.md`)**: Prevents 5 RPM / 20 RPD models (`Gemini 3.8 Flash`, `3.6 Flash`) from chaining multiple sequential tool calls or subagents.

## Fresh Installation

1. Install standard Antigravity CLI so `~/.local/bin/agy` exists.
2. Clone this repo and run `./install.sh`:

    git clone https://github.com/Odyssious13/agy-cli_mod.git /mnt/storage/projects/agy-cli_mod
    cd /mnt/storage/projects/agy-cli_mod
    ./install.sh

3. Add your API keys to `/mnt/storage/.env`.
4. Run `agy` (OAuth) or `agy-api` (API) from any project directory.

## Syncing Live Edits Back to Git

    cd /mnt/storage/projects/agy-cli_mod
    ./sync-from-live.sh
