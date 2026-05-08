# Security Policy

## Supported Versions

Only the latest tagged release of `chrome-bridge` receives security updates.
Pre-release/development builds from `main` are best-effort.

| Version  | Supported          |
| -------- | ------------------ |
| latest   | :white_check_mark: |
| < latest | :x:                |

## Reporting a Vulnerability

**Please do NOT open public GitHub issues for security vulnerabilities.**

Use one of these private channels:

1. **GitHub Security Advisories (preferred)** — open a private advisory at
   https://github.com/yolo-labz/chrome-bridge/security/advisories/new
2. **Email** — contact the maintainer directly via the email listed on
   https://github.com/phsb5321

### What to include

- Affected version (commit SHA or release tag)
- Reproduction steps or proof-of-concept
- Impact assessment (what data/system is at risk)
- Suggested mitigation (optional)

### Response SLA

- **Acknowledgement:** within 72 hours
- **Triage + initial assessment:** within 7 days
- **Fix or mitigation:** target 30 days for high/critical, 90 days for medium/low

We will credit reporters in the release notes unless anonymity is requested.

## Verifying Releases

Every release is published with cryptographic provenance via Sigstore.
Verify a downloaded release artifact:

```bash
gh attestation verify <artifact> --repo yolo-labz/chrome-bridge
```

SBOMs (CycloneDX 1.7 + SPDX 2.3) are attached to each GitHub Release for
supply-chain auditing.

## Threat Model

`chrome-bridge` runs a localhost-only HTTP relay (default `127.0.0.1:9224`)
that brokers between a Chrome extension and a CLI on the same machine. It
does not expose any network surface. The relay trusts any process on the
local host that can bind/connect to the loopback interface.

Out-of-scope for this project:
- Network-level isolation (use OS firewall / namespaces)
- Multi-user host hardening (single-user dev workstation assumption)
- Browser fingerprinting resistance
