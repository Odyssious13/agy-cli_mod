# Sourced by the agent launchers (claude, agy). Agents and everything they start must
# never play audio or draw on the user's screen, so children inherit an environment
# with no display and no sound server. Headless/offscreen backends still work.
unset DISPLAY WAYLAND_DISPLAY XAUTHORITY
export PULSE_SERVER=unix:/nonexistent PIPEWIRE_REMOTE=/nonexistent   # PulseAudio, PipeWire (and ALSA routed through them)
export SDL_AUDIODRIVER=dummy SDL_VIDEODRIVER=offscreen AUDIODEV=null
export QT_QPA_PLATFORM=offscreen MOZ_HEADLESS=1 BROWSER=echo     # Qt apps, Firefox, xdg-open/webbrowser fallbacks
export SD_QUIET=1                                                # lets scripts check they run under an agent
