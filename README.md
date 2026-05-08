# chrome-bridge

> Trusted-event Chrome automation bridge for the yolo-labz fleet — MV3 first-party extension loaded into a dedicated **Profile-Auto** Chrome instance, paired with a localhost relay daemon (`cb` CLI) that any sibling plugin (`claude-mac-chrome`, `lcc`, `wa`) can shell out to.

Solves the `isTrusted=true` event-trust gate on Vue/React SPAs and the JA4+ TLS fingerprinting gate on regulated sites — without exposing Pedro's daily Chrome to CDP attach (catastrophic blast radius), without sending his cookies to a third-party SaaS like Browserbase (principle IX violation), and without the Patchright bundled-Chromium signature that LinkedIn Q1 2026 BrowserGate scanner now flags.

## Architecture (one-page)

```
┌─────────────────────┐                      ┌─────────────────────────┐
│  Sibling plugin /   │   shell out          │  cli/cb (Python stdlib) │
│  Claude Code task   │ ────────────────────▶│  127.0.0.1:9224 relay   │
└─────────────────────┘                      └─────────────────────────┘
                                                       │
                                                       │ long-poll JSON
                                                       ▼
                                  ┌──────────────────────────────────────────┐
                                  │  Profile-Auto Chrome (CfT 145)           │
                                  │  ─────────────────────────────────       │
                                  │  ext/service-worker.js  ◀── polls relay  │
                                  │  ext/main-world-capture.js (capture)     │
                                  │  chrome.cookies / scripting / debugger   │
                                  └──────────────────────────────────────────┘
                                                       │
                                                       │ trusted events / Bearer auth
                                                       ▼
                                  ┌──────────────────────────────────────────┐
                                  │  Target site (Upwork / blog / dokku)     │
                                  └──────────────────────────────────────────┘
```

**Daily Chrome** — Pedro's main browsing profile — is **not touched**. Profile-Auto runs in a separate `--user-data-dir` and is only launched when automation work is pending.

## Why Chrome for Testing (CfT)

Chrome 137+ stable / beta / dev / canary all hard-block `--load-extension` regardless of `--disable-features` flags. Chromium fails macOS Tahoe Gatekeeper (unsigned). **Chrome for Testing** is Google's official testing distribution: same Blink/V8 build as Stable, but without the brand-restriction enforcement on `--load-extension`. Bundled and signed via Microsoft's Playwright CDN. Install once:

```sh
uv tool install patchright
uvx --from patchright patchright install chromium
```

The launcher resolves the CfT binary at `~/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app`.

## Three-tier surface taxonomy

| Tier | Example | Mechanism via chrome-bridge |
|------|---------|------------------------------|
| **A — stealth-critical** (LinkedIn primary, banking, G&P-visible) | `cliclick` + clipboard-handoff. **Never** `chrome.debugger`, **never** automation. STEALTH_DOMAINS list in `service-worker.js` refuses jobs targeting these even if relay sent them. |
| **B — semi-stealth** (Upwork primary, Calendly admin, Twitter secondary) | `cb gql` direct GraphQL via `chrome.cookies` Bearer first; `cb debug-click` second when surface insists on UI. Behavioural jitter from `cb debug-type`. |
| **C — Pedro-owned infra** (sonarqube / dokku / infisical / ProxMox) | Direct REST/SSH first (no chrome-bridge needed). `cb` only when admin auth lives in a browser cookie. |
| **D — escape hatch** (public scraping, no account at risk) | Patchright + residential proxy in a separate repo. Not a `chrome-bridge` consumer. |

## Quick start

```sh
# 1. Launch Profile-Auto Chrome with the extension loaded.
#    Auto-starts the cb relay daemon on 127.0.0.1:9224.
./launch/profile-auto.sh --bg

# 2. Health check.
./cli/cb ping

# 3. Cookies.
./cli/cb cookies https://www.upwork.com/

# 4. Direct GraphQL with Bearer extracted from a cookie.
./cli/cb gql https://www.upwork.com/api/graphql/v1 \
  --alias findSkills \
  --query "query searchSkillsByPrefLabel(\$query: String!, \$type: OntologyEntityType!, \$status: OntologyEntityStatus!, \$ordering: String!, \$limit: Int!) { ontologyElementsSearchByPrefLabel(filter: {preferredLabel_any: \$query, type: \$type, entityStatus_eq: \$status, sortOrder: \$ordering, limit: \$limit}) { id preferredLabel } }" \
  --vars '{"query":"AI Agent Development","type":"SKILL","status":"ACTIVE","ordering":"match-start","limit":5}' \
  --bearer-cookie profile_vv_gql_token

# 5. Capture XHRs in MAIN-world.
./cli/cb capture-install <tabId> --pattern "graphql"
# ... user clicks something ...
./cli/cb capture-drain <tabId>

# 6. Trusted click via chrome.debugger.Input.
./cli/cb debug-click <tabId> 659 402

# 7. Trusted typing with humanesque jitter.
./cli/cb debug-type <tabId> "hello world"
```

## Verb reference

| `cb` verb | What it does | Behind the scenes |
|-----------|--------------|--------------------|
| `cb daemon` | start the localhost relay | `http.server` on 127.0.0.1:9224 |
| `cb ping` | health-check the bridge | sends `kind: "ping"` |
| `cb cookies <url>` | list cookies for url | `chrome.cookies.getAll` |
| `cb cookies-bearer <url> <name>` | print just one cookie's value | for shelling into `--bearer` |
| `cb gql <url> --query ... --vars ... [--bearer / --bearer-cookie]` | POST GraphQL with Bearer auth | service-worker `fetch` with `credentials: "include"` |
| `cb tabs` | list open tabs | `chrome.tabs.query` |
| `cb tab-update <tabId> --url ... --active true` | navigate a tab | `chrome.tabs.update` |
| `cb eval <tabId> <code> [--world MAIN/ISOLATED]` | run JS in tab, get result | `chrome.scripting.executeScript` |
| `cb capture-install <tabId> [--pattern STR_OR_re:REGEX]` | install MAIN-world fetch+XHR interceptor | injects `main-world-capture.js` |
| `cb capture-drain <tabId>` | get + clear captured requests | reads `window.__cbCapturedRequests` |
| `cb debug-click <tabId> <x> <y>` | trusted click at viewport coords | `chrome.debugger.attach` + `Input.dispatchMouseEvent` |
| `cb debug-type <tabId> <text>` | trusted typing with 30-110ms jitter | `chrome.debugger.attach` + `Input.insertText` |

## STEALTH_DOMAINS guard (defense in depth)

`extension/service-worker.js` hard-blocks any job whose URL hostname matches the `STEALTH_DOMAINS` set. Currently `linkedin.com` is hard-coded. Even if the relay sent a job to `cb gql --url https://www.linkedin.com/...`, the service worker returns `{ok:false, error:"stealth-blocked"}` before the fetch ever leaves the extension. This is intentional belt-and-suspenders for Pedro's principle IX — adding a Tier-A site to the bridge requires editing the extension source, never just the relay.

## What's been validated

- Extension loads cleanly into CfT 145, SW polls relay every 0.4s
- `cb cookies` / `cb gql` / `cb scripting.eval` / `cb capture.install` / `cb debugger.click` all round-trip end-to-end against Pedro's logged-in Upwork session
- 20 Upwork skill ontology UIDs resolved via `findSkills` (5 not-in-ontology gaps documented)
- 26 Upwork mutations identified by JS chunk grepping; canonical bodies captured for `updateTalentProfileTitle`, `updateTalentProfileDescription`, `updateTalentProfileHourlyRate`, `updateTalentProfileSkills`, `updateShowProjectOnProfile`, `updateTalentLanguageRecords`, `addPortfolioProject` (partial — relies on imported fragments)
- `updateTalentProfileTitle` mutation verified working (idempotent test returned `status:true` + persisted state matched)
- **Found:** `updateTalentProfileSkills` is a silent-no-op for Pedro's profile pre-28/05/2026 (Upwork specialized-profiles deprecation transition). See `captures/upwork-skills-pipeline.md`.

## Future phases

- **P2** — capture portfolio + catalog mutations (currently rely on imported fragments — need to resolve the webpack chunk that defines `n.g`, `n.a`, `n.i` for `createTalentPortfolio`)
- **P3** — Haiku 4.5 LLM-fallback resolver — `cb resolve --ax-tree` reads accessibility tree, asks Haiku "which element is the Save button?", returns coords. Gated by `--budget-usd 0.10` per call.
- **P4** — Profile management — manifest.lock pattern matching `wa` plugin (SessionStart hook diffs bundled vs installed extension, reinstalls on drift)
- **P5** — generalize to Instagram + future sites (per the synthesis doc roadmap)

## License

MIT. See `LICENSE`.
