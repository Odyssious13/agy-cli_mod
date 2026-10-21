# Sourced by the app wrappers in this folder. Gives each app a private HOME on the drive
# so configs, caches, logs and licence files never land in the real ~ (storage rule).
# Usage: sd_env <app-home-dir>
sd_env() {
  local h="$1"
  mkdir -p "$h/.config" "$h/.local/share" "$h/.cache" /mnt/storage/.claude-workspace/tmp
  # Convenience link so file dialogs that open in the fake HOME can reach the drive.
  [ -e "$h/storage" ] || ln -s /mnt/storage "$h/storage"
  export HOME="$h" XDG_CONFIG_HOME="$h/.config" XDG_DATA_HOME="$h/.local/share" XDG_CACHE_HOME="$h/.cache"
  export TMPDIR=/mnt/storage/.claude-workspace/tmp
}

# Isolated npm paths on /mnt/storage
export NPM_CONFIG_PREFIX="/mnt/storage/.npm-global"
export NPM_CONFIG_CACHE="/mnt/storage/.npm-cache"
case ":$PATH:" in
  *":/mnt/storage/bin:"*) ;;
  *) PATH="/mnt/storage/bin:$PATH" ;;
esac
case ":$PATH:" in
  *":/mnt/storage/.npm-global/bin:"*) ;;
  *) PATH="/mnt/storage/.npm-global/bin:$PATH" ;;
esac
export PATH
