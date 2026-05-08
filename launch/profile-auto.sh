#!/usr/bin/env bash
# Launch a dedicated Chrome instance ("Profile-Auto") that loads chrome-bridge
# unpacked. Daily Chrome is left untouched — separate --user-data-dir.
#
# Flags:
#   --silent-debugger-extension-api  hides the yellow "extension started debugging" infobar
#   --user-data-dir=...              isolated profile dir under ~/Library/.../Chrome-Auto
#   --load-extension=...             loads chrome-bridge unpacked
#   --no-first-run --no-default-browser-check  suppress new-profile chrome of trust
#
# Usage:
#   ./launch/profile-auto.sh                     # foreground, attached to terminal
#   ./launch/profile-auto.sh --bg                # background, logs to /tmp
#
# Pre-req: cb daemon must be running (or will be started by the plugin SessionStart hook).

set -euo pipefail

# Resolve repo root (script lives in launch/, repo is parent).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EXTENSION_DIR="$REPO_ROOT/extension"

# Per-OS defaults. Override either via env (CB_PROFILE_DIR / CB_CHROME_BIN).
#
# macOS: candidate chain, first match wins. All candidates must be UNBRANDED
# (i.e. NOT Google-branded Chrome stable/beta/dev/canary) since Chrome 137+
# enforces `DisableLoadExtensionCommandLineSwitch` even with the
# --disable-features flag, silently dropping --load-extension.
#
# Order:
#   1. Homebrew cask `chromium` (Eloston ungoogled-chromium build, code-signed
#      ad-hoc, requires `xattr -dr com.apple.quarantine /Applications/Chromium.app`
#      on first launch — see README "macOS install" section)
#   2. Chrome for Testing (CfT) bundled by Patchright/Playwright. Same Blink/V8
#      as Stable, but the brand-restriction is off. Code-signed by Microsoft +
#      Google joint sigs; clears Gatekeeper without quarantine surgery.
#   3. /Applications/Chromium.app (manual install, e.g. from chromium.org or
#      a download not via Homebrew cask)
#
# Linux: nix `chromium` from nixpkgs is the default — open-source Chromium
# build (not Google-branded Chrome), so the brand-restriction policy
# (DisableLoadExtensionCommandLineSwitch) is moot, and --load-extension works
# out of the box. Profile dir mirrors the `chromium-profile` wrapper layout
# under XDG_DATA_HOME so it composes with existing per-profile launches.
case "$(uname -s)" in
  Darwin)
    PROFILE_DEFAULT="$HOME/Library/Application Support/Google/Chrome-Auto"
    # Probe each candidate's --version output and accept ONLY when the first
    # token is literally "Chromium". Mirrors the Linux brand-guard.
    _cb_is_unbranded_chromium_darwin() {
      local bin="$1"
      [[ -x "$bin" ]] || return 1
      local ver
      ver="$("$bin" --version 2>/dev/null)" || return 1
      # CfT identifies as "Google Chrome for Testing", but the binary honors
      # --load-extension because the brand-restriction policy is gated on the
      # full brand string. Accept both forms.
      [[ "$ver" == Chromium\ * || "$ver" == "Google Chrome for Testing"\ * ]]
    }
    _cb_darwin_candidates=(
      # Homebrew cask `chromium` (ungoogled-chromium)
      "/Applications/Chromium.app/Contents/MacOS/Chromium"
      # Chrome for Testing (Patchright/Playwright bundle, version-pinned dir)
      "$HOME/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
      # Common fallback paths
      "/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"
    )
    # Also probe any chromium-1NNN dir under ms-playwright (CfT version drift)
    if [[ -d "$HOME/Library/Caches/ms-playwright" ]]; then
      while IFS= read -r -d '' _cb_cft; do
        _cb_darwin_candidates+=("$_cb_cft")
      done < <(find "$HOME/Library/Caches/ms-playwright" \
        -maxdepth 5 -type f -name "Google Chrome for Testing" -print0 2>/dev/null)
    fi
    CHROME_DEFAULT=""
    for _cb_cand in "${_cb_darwin_candidates[@]}"; do
      if _cb_is_unbranded_chromium_darwin "$_cb_cand"; then
        CHROME_DEFAULT="$_cb_cand"
        break
      fi
    done
    unset _cb_darwin_candidates _cb_cand _cb_cft
    ;;
  Linux)
    PROFILE_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/browser-automation/profiles/auto"
    # MUST be UNBRANDED Chromium — Google-branded Chrome (incl. nix
    # `google-chrome` package) enforces the brand-restriction policy
    # `DisableLoadExtensionCommandLineSwitch` even when the
    # --disable-features flag is passed, so --load-extension is silently
    # ignored and the chrome-bridge MV3 SW never registers. Verified on
    # Chrome 148.0.7778.96 (06/05/2026, NixOS desktop).
    #
    # Detection strategy: probe each candidate's `--version` output and
    # accept ONLY when the first token is literally "Chromium". Reject
    # "Google" branding even if the binary name happens to be "chromium"
    # (some distros symlink chromium → google-chrome).
    _cb_is_unbranded_chromium() {
      local bin="$1"
      [[ -x "$bin" ]] || return 1
      local ver
      ver="$("$bin" --version 2>/dev/null)" || return 1
      [[ "$ver" == Chromium\ * ]]
    }
    CHROME_DEFAULT=""
    # Candidates in priority order: PATH chromium, the `chromium-profile`
    # wrapper's pinned target (resolved at runtime by parsing the wrapper),
    # then any chromium under /run/current-system/sw/bin (NixOS system pkg).
    _cb_candidates=()
    if command -v chromium >/dev/null 2>&1; then
      _cb_candidates+=("$(command -v chromium)")
    fi
    if command -v chromium-profile >/dev/null 2>&1; then
      # Extract the `exec /nix/store/.../bin/chromium` line from the wrapper
      # so we inherit whatever unbranded chromium home-manager pinned.
      _cb_pinned="$(awk '/^exec [^ ]+chromium/ {print $2; exit}' \
        "$(command -v chromium-profile)" 2>/dev/null || true)"
      [[ -n "$_cb_pinned" ]] && _cb_candidates+=("$_cb_pinned")
    fi
    [[ -x /run/current-system/sw/bin/chromium ]] \
      && _cb_candidates+=("/run/current-system/sw/bin/chromium")
    for _cb_cand in "${_cb_candidates[@]}"; do
      if _cb_is_unbranded_chromium "$_cb_cand"; then
        CHROME_DEFAULT="$_cb_cand"
        break
      fi
    done
    unset _cb_candidates _cb_cand _cb_pinned
    ;;
  *)
    echo "error: unsupported OS: $(uname -s)" >&2
    exit 2
    ;;
esac
PROFILE_DIR="${CB_PROFILE_DIR:-$PROFILE_DEFAULT}"
CHROME_BIN="${CB_CHROME_BIN:-$CHROME_DEFAULT}"

if [[ -z "$CHROME_BIN" || ! -x "$CHROME_BIN" ]]; then
  echo "error: Chrome not found at '${CHROME_BIN:-<empty>}'" >&2
  if [[ "$(uname -s)" == "Linux" ]]; then
    echo "       Linux requires UNBRANDED Chromium (Google Chrome blocks --load-extension)." >&2
    echo "       Install: nix-env -iA nixos.chromium  OR  set CB_CHROME_BIN=/path/to/chromium" >&2
  else
    echo "       set CB_CHROME_BIN to override" >&2
  fi
  exit 2
fi
# Linux-only brand guard: refuse to launch Google-branded Chrome since
# --load-extension is silently dropped (chrome-bridge SW never registers).
if [[ "$(uname -s)" == "Linux" ]]; then
  _cb_brand="$("$CHROME_BIN" --version 2>/dev/null | awk '{print $1}')"
  if [[ "$_cb_brand" != "Chromium" ]]; then
    echo "error: $CHROME_BIN is '$_cb_brand'-branded; chrome-bridge requires unbranded Chromium" >&2
    echo "       (Google Chrome 137+ enforces DisableLoadExtensionCommandLineSwitch even with --disable-features)" >&2
    echo "       set CB_CHROME_BIN to an unbranded chromium binary" >&2
    exit 2
  fi
  unset _cb_brand
fi

if [[ ! -d "$EXTENSION_DIR" ]]; then
  echo "error: extension dir missing: $EXTENSION_DIR" >&2
  exit 2
fi

mkdir -p "$PROFILE_DIR"

# Start cb relay if not already up.
if ! curl -sf "http://127.0.0.1:9224/health" >/dev/null 2>&1; then
  echo "[cb] starting relay daemon..."
  nohup "$REPO_ROOT/cli/cb" daemon --port 9224 \
    >"$HOME/.local/state/chrome-bridge/relay.log" 2>&1 &
  sleep 0.4
  curl -sf "http://127.0.0.1:9224/health" >/dev/null || {
    echo "error: relay failed to start; see $HOME/.local/state/chrome-bridge/relay.log" >&2
    exit 3
  }
fi

ARGS=(
  "--user-data-dir=$PROFILE_DIR"
  "--load-extension=$EXTENSION_DIR"
  "--disable-extensions-except=$EXTENSION_DIR"
  "--silent-debugger-extension-api"
  "--no-first-run"
  "--no-default-browser-check"
  # DisableLoadExtensionCommandLineSwitch is enabled by default in Chrome 137+
  # stable, which kills --load-extension. Disabling that feature restores it.
  # DialMediaRouteProvider + InterestFeedContentSuggestions are noise.
  "--disable-features=DisableLoadExtensionCommandLineSwitch,DialMediaRouteProvider,InterestFeedContentSuggestions"
  "--disable-popup-blocking"
  # Window banner so Pedro never confuses Profile-Auto with daily Chrome.
  "--window-name=PROFILE-AUTO"
)

if [[ "${1:-}" == "--bg" ]]; then
  nohup "$CHROME_BIN" "${ARGS[@]}" \
    >"$HOME/.local/state/chrome-bridge/chrome.log" 2>&1 &
  echo "[cb] Profile-Auto Chrome PID=$!"
  echo "[cb] log: $HOME/.local/state/chrome-bridge/chrome.log"
else
  exec "$CHROME_BIN" "${ARGS[@]}"
fi
