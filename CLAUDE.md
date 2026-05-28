# CLAUDE.md — chrome-bridge

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Purpose

Trusted-event Chrome automation bridge. An MV3 first-party browser extension loaded into a dedicated **Profile-Auto** Chrome instance, paired with a localhost relay daemon (`cli/cb`, Python stdlib) on `127.0.0.1:9224` that any sibling plugin can shell out to.

Solves two gates that `chrome.debugger`-from-CDP-attach and AppleScript cannot reach on Chromium under Manifest V3:

1. **`isTrusted=true` event-trust** on Vue/React SPAs whose handlers reject synthetic events.
2. **First-party network identity** — `chrome.cookies` + `chrome.scripting` in MAIN world preserve the renderer's JA4+ TLS fingerprint and credential store.

Daily Chrome is **not touched**: Profile-Auto runs in a separate `--user-data-dir` and is only launched when automation is pending. This is **cross-platform (macOS + Linux)**, in contrast to the sibling [`yolo-labz/claude-mac-chrome`](https://github.com/yolo-labz/claude-mac-chrome) which is macOS-only AppleScript over Pedro's daily Chrome.

A `STEALTH_DOMAINS` set in `extension/service-worker.js` hard-blocks Tier-A surfaces (LinkedIn, banking) at the extension boundary — the relay cannot reach those even if asked.

## Stack

- **CLI:** Python 3.12 stdlib only (no third-party deps). `argparse` + `http.server` + `urllib`. Single-file `cli/cb`.
- **Extension:** Vanilla JS (no React, no bundler). MV3 service worker (`extension/service-worker.js`), ISOLATED-world content script (`content-bridge.js`), MAIN-world capture shim (`main-world-capture.js`).
- **Launcher:** Bash 4+ portable (`launch/profile-auto.sh`). Per-OS Chrome candidate chain + brand-guard refusing Google-branded Chrome (137+ enforces `DisableLoadExtensionCommandLineSwitch` even with `--disable-features`).
- **Tests:** No `tests/` directory in the repo yet. Smoke gates run inside CI workflows (see below).
- **Platforms:** macOS 13+ (Intel + Apple Silicon) via Homebrew `chromium` cask or Patchright-bundled Chrome for Testing; Linux via nixpkgs `chromium` or any distro-packaged unbranded Chromium on `$PATH`. Google-branded Chrome is rejected.
- **License:** MIT.

## Repo layout

```text
.claude-plugin/
  plugin.json             # name, version, description (required by Claude Code)
cli/
  cb                      # Python 3.12 stdlib CLI + relay daemon (single file)
extension/
  manifest.json           # MV3 manifest — cookies/scripting/debugger/tabs/storage/alarms/webRequest
  service-worker.js       # polling SW, job dispatch, STEALTH_DOMAINS guard
  content-bridge.js       # ISOLATED-world content script (stub)
  main-world-capture.js   # MAIN-world fetch+XHR interceptor (web_accessible_resource)
launch/
  profile-auto.sh         # per-OS Chrome candidate chain + brand-guard + relay-autostart
scripts/                  # Python automations consuming `cb` (7 upwork-*.py + 1 .sh)
captures/                 # JSON/Markdown snapshots from `cb capture-*` sessions
.github/workflows/        # ci.yml + release.yml + osv-scanner.yml + scorecard.yml
LICENSE                   # MIT
SECURITY.md               # vulnerability reporting (GitHub Private Vulnerability Reporting)
```

No `tests/` directory exists yet — testing is exercised through CI smoke gates and ad-hoc round-trips against Profile-Auto (per `README.md` "What's been validated").

## Run / build / test

```bash
# Launch Profile-Auto Chrome with extension loaded (also auto-starts cb relay)
bash launch/profile-auto.sh --bg

# Verbs (full reference in README.md)
./cli/cb ping
./cli/cb cookies https://www.upwork.com/
./cli/cb gql https://www.upwork.com/api/graphql/v1 --query - --vars '{}'
./cli/cb tabs
./cli/cb capture-install <tabId> --pattern graphql
./cli/cb capture-drain <tabId>
./cli/cb debug-click <tabId> 659 402
./cli/cb debug-type <tabId> "hello"

# Smoke gates (mirror CI)
python3 -m py_compile cli/cb scripts/*.py
node --check extension/*.js
shellcheck launch/*.sh
# manifest.json schema validation — see .github/workflows/ci.yml `manifest-validate` job
```

CI workflows (`.github/workflows/`):

- **`ci.yml`** — `shellcheck` on `launch/*.sh`, Python `py_compile` on `cli/cb` + `scripts/*.py`, `node --check` on `extension/*.js`, ad-hoc manifest validator that asserts MV3 + presence of every referenced JS file.
- **`release.yml`** — tag-triggered (`v*.*.*`). Builds reproducible `git archive` tarball + SHA-256 manifest, generates CycloneDX 1.7 + SPDX 2.3 SBOMs via `anchore/sbom-action`, signs via `actions/attest-build-provenance@v4.1.0` (SHA `a2bbfa25375fe432b6a289bc6b6cd05ecd0c4c32`). PR #6 (open, draft) adds cosign keyless OIDC, `permissions: {}` deny-all + per-job re-grant, and `step-security/harden-runner` audit baseline.
- **`osv-scanner.yml`** — OSV-Scanner V2 reusable workflow, weekly Monday 06:00 UTC + PR + push.
- **`scorecard.yml`** — OpenSSF Scorecard, weekly Tuesday 07:00 UTC + push to main + workflow_dispatch.

## Conventions

- **One concern per PR.** Constitution Principle VIII — split sign-path + dev-workflow + docs into separate sibling PRs.
- **Conventional Commits + DCO + Co-Author trailer.** Subject ≤72 chars. `feat/fix/refactor/chore/docs`.
- **Worktree-first.** Every PR authored in `~/Documents/Code/yolo-labz-chrome-bridge-NNN-slug/`. Main worktree stays on `main`, clean, forever.
- **SHA-pin every GitHub Action.** Full 40-char commit SHA with trailing `# vX.Y.Z` comment. Dependabot's regex needs the version comment to recognize the pin.
- **Never re-tag a release.** `slsa-verifier` validates against the commit SHA at signing time; cut `vX.Y.Z+1` on botched publishes.
- **Stealth canon.** Adding a domain to the relay's reach requires editing `STEALTH_DOMAINS` in `extension/service-worker.js` — never just the CLI. Belt-and-suspenders so a misrouted relay job cannot exfiltrate Tier-A surfaces.

## Architecture

```text
sibling plugin / Claude task
        │  (shell out: ./cli/cb <verb> …)
        ▼
cli/cb (Python stdlib) ◀──▶ 127.0.0.1:9224 (relay daemon, same process)
        ▲
        │  long-poll JSON (GET /poll?wait=20)
        │
extension/service-worker.js (MV3 SW, polled via chrome.alarms 0.4min cadence)
        │  dispatch by `kind` → chrome.{cookies,scripting,tabs,debugger,webRequest}
        │  STEALTH_DOMAINS check on every URL-bearing job
        ▼
Profile-Auto Chrome (unbranded Chromium or Chrome-for-Testing)
        ▼
target site (Upwork / blog / dokku / etc.)
```

Job verbs implemented in `service-worker.js` `handleJob()`:

| Kind | Mechanism |
|---|---|
| `ping` | health echo with UA + ts |
| `cookies` | `chrome.cookies.{get,getAll}` for a URL |
| `gql` | `fetch(POST)` with `credentials: "include"` + optional `Bearer` |
| `tabs.query` / `tabs.create` / `tabs.update` | `chrome.tabs.*` |
| `scripting.eval` | `chrome.scripting.executeScript` in MAIN or ISOLATED |
| `capture.install` / `capture.drain` | Inject `main-world-capture.js`, read/clear `window.__cbCapturedRequests` |
| `network.start` / `network.drain` / `network.stop` | `chrome.webRequest.onBeforeRequest` recorder (survives reloads) |
| `debugger.click` / `debugger.type` | `chrome.debugger.attach` + `Input.dispatchMouseEvent`/`Input.dispatchKeyEvent` with 30-110ms jitter |

Service-worker keepalive: `chrome.alarms.create("cb-poll", { periodInMinutes: 0.4 })` plus a tight async loop (500ms cadence) while SW is alive. MV3 SWs are non-persistent — the alarm re-wakes the SW after each 25s eviction window.

`extension/manifest.json` requests `cookies`, `scripting`, `debugger`, `tabs`, `storage`, `alarms`, `webRequest`, with host permissions for `https://*.upwork.com/*`, `https://*.linkedin.com/*` (refused by `STEALTH_DOMAINS`), and `127.0.0.1:9224` for the relay round-trip.

## STEALTH_DOMAINS guard (defense in depth)

`extension/service-worker.js` hard-blocks any URL-bearing job whose hostname matches the `STEALTH_DOMAINS` set. Currently `linkedin.com` (Tier-A: clipboard-handoff only) and a placeholder for banking. The relay can queue any job; the extension returns `{ok:false, error:"stealth-blocked"}` before the fetch ever leaves Chrome. Adding to the bridge requires editing the extension source, never just the relay.

## Cross-references

- **Vault canon:** `~/.claude/CLAUDE.md` + `~/Documents/Code/CLAUDE.md` (workspace org rules + ownership rule).
- **Constitution:** `~/Documents/Code/yolo-labz/.specify/memory/constitution.md` v1.0.0 (Principles I–XV, all non-negotiable).
- **Spec:** `024-yolo-labz-portfolio-consolidation-2026Q2`, plan §7 W5 — Phase 4 `/init` sibling PRs across the fleet.
- **Audit:** [`phsb5321/notes-work#24`](https://github.com/phsb5321/notes-work/pull/24).
- **Sibling repo (different OS scope):** [`yolo-labz/claude-mac-chrome`](https://github.com/yolo-labz/claude-mac-chrome) — macOS-only AppleScript over Pedro's daily Chrome, with a 15-layer safety gauntlet. `chrome-bridge` is the cross-platform Profile-Auto sibling that solves the trust gate via first-party `chrome.debugger` + first-party MAIN-world `fetch`.
- **Class-leader (release-engineering):** [`yolo-labz/fand`](https://github.com/yolo-labz/fand) — the canonical layout this `/init` PR mirrors.

## Sonar gap (Pedro action — out of this PR)

`chrome-bridge` currently has **no SonarQube wiring**. As of the 2026-05-27 secrets probe, no `SONAR_TOKEN` exists at the repo, org, or environment level on this repository.

Before a Sonar-workflow PR can land, Pedro must:

1. Create the Sonar project at the SonarCloud / self-hosted instance for `yolo-labz/chrome-bridge`.
2. Mint a project-scoped analysis token (per release-engineering canon — never a user token; never an org-wide token).
3. Add it to GitHub Actions as `SONAR_TOKEN` repo secret.

Only then is the Sonar workflow safe to add as a follow-up PR. Tracking this as a Pedro-gated dependency, NOT a blocker on this `/init` PR.

## Active feature work pointers

- **PR #6** (open, draft) — `feat(release): cosign keyless OIDC + permissions{} deny-all + harden-runner audit`. Adds `sigstore/cosign-installer@v3.7.0` keyless signing (OIDC issuer `token.actions.githubusercontent.com`), workflow-level `permissions: {}` deny-all + per-job re-grant, `step-security/harden-runner@v2.12.1` with `egress-policy: audit`. Gated on PR-A (wa) class-leader sign-off per spec 024 §3 DAG.

## Release verification

```bash
# Primary path — GitHub native attestations (single command, no cosign install)
TAG=v0.1.0
gh release download "$TAG" --repo yolo-labz/chrome-bridge
gh attestation verify "chrome-bridge-${TAG}.tar.gz" --repo yolo-labz/chrome-bridge

# All three release artifacts share one Rekor entry — verify each in the loop
for f in "chrome-bridge-${TAG}.tar.gz" sbom.cdx.json sbom.spdx.json; do
  gh attestation verify "$f" --repo yolo-labz/chrome-bridge && echo "  ok $f"
done
```

`gh attestation verify` exits 0 silently on success. Add `--format json` to inspect the full DSSE envelope, Rekor `logIndex`, and `sourceRepositoryDigest`.

Advanced / offline verification (`cosign verify-blob --bundle`) becomes available once PR #6 lands and the next release publishes `chrome-bridge-vX.Y.Z.tar.gz.cosign.bundle`. Cosign OIDC issuer is always `https://token.actions.githubusercontent.com` — never the interactive `github.com/login/oauth` URL.

If any verification fails: **do not install**, file a GitHub Security Advisory via `/security/advisories/new`.

## License

MIT — see [LICENSE](./LICENSE).
