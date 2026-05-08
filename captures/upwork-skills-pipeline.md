---
title: Upwork Skills 20-list — GraphQL pipeline + the May-28 transition trap
captured_via: chrome-bridge cb gql + scripting.eval + debugger.click against CfT 145 (Profile-Auto)
captured_at_brt: 27/04/2026
status: PIPELINE BUILT — but updateTalentProfileSkills SILENT-NO-OPS for Pedro's profile pre-28/05/2026 (Upwork specialized-profiles deprecation)
---

# 27/04/2026 — SOLVED via trusted modal drive

The legacy `updateTalentProfileSkills` GraphQL mutation no-ops, BUT the modal
Save button fires through the migration-aware Vue code path which **does**
work. Resolved by driving the modal end-to-end with `chrome.debugger.Input.*`
trusted events. See `scripts/upwork-skills-modal-drive.py` — single command,
~30 sec wall time, drives 7 chip removes + 10 chip adds + 1 Save click.

Verified 27/04/2026 14:22 BRT against Pedro's profile (`~01dae7197e964ddf3f`):
went from 17 skills (Python, TS, AWS, Docker, Terraform, ML, Cloud Arch, API
Dev, DevOps, Web Scraping, Data Extraction, Automation, Next.js, React,
Node.js, FastAPI, Selenium WebDriver) → 20 target skills (AI tier first).
Read-after-write 20/20 IDs match.

Two non-obvious gates the script handles:
- Save button is `disabled` while typeahead input has uncommitted text
  (Vue prevents accidental "user typed but didn't pick" loss). Script clicks
  the in-modal "Clear Input" button after each suggestion-pick + before Save.
- Suggestion DOM lives outside `[role="dialog"]` (Vue Teleport portal). The
  exact-text + `:not([within ol.air3-sortable-list])` filter picks the
  fresh suggestion, never the existing chip.

Reasoning that backed out the silent-no-op behaviour: see "How direct GraphQL
no-ops" below — kept for archaeology + post-28/05 re-capture plan.

# How direct GraphQL no-ops (archaeology — DEPRECATED PATH)

Upwork is killing specialized profiles 28/05/2026 ("One profile, evolved to win
more work" announcement banner is currently shown on every freelancer profile
page). During the transition window:

- `updateTalentProfileSkills($input: TalentProfileSkillsInput!)` accepts our
  payload, returns `{data:{updateTalentProfileSkills:{status:true}}}` HTTP 200
- BUT the actual stored skill set does NOT change
- This was verified empirically: sending REVERSED current 17 UIDs returned
  `status:true` but skills stayed in original rank order
- Sending the 20-list also no-oped — same input shape per the JS source
  (`{input:{skills:[{skillID:uid}]}}`)

**Why:** The legacy `updateTalentProfileSkills` mutation is decoupled from the
new unified-profile schema. Writes during transition target a deprecated
table. Frontend `Save` click in `/freelancers/.../modal-skills-edit` modal
fires NO GraphQL request when nothing changed (Vue dirty-check no-op). When
something DOES change, it likely fires a NEW mutation that hasn't been published
to the bundles we scanned yet.

**Mitigations:**

1. **Wait until 29/05/2026** (post-migration) and re-capture. The new mutation
   should be in the bundles by then.
2. **Operator-checklist path** (5–7 min Algolia typeahead manual flow per
   `2. Areas/👷 Work/UPWORK-OPERATOR-CHECKLIST.md` Batch 1) — proven works
   because the modal save fires the production code path with whatever
   migration-aware logic Upwork is using internally.
3. **Capture the real mutation** by ARMING `cb capture.install` → having
   operator add ONE skill manually → drain. The actual outgoing mutation will
   reveal the new schema.

The other captured mutations (`updateTalentProfileTitle`, `updateTalentProfile-
Description`, `updateTalentProfileHourlyRate`, `updateTalentLanguageRecords`,
`updateShowProjectOnProfile`) are NOT affected by the transition — verified
`updateTitle` returns valid `status:true` and persists.



# Upwork Skills 20-list — capture-free GraphQL pipeline

## Endpoint

```
POST https://www.upwork.com/api/graphql/v1?alias=<aliasName>
```

## Auth

`Authorization: Bearer <profile_vv_gql_token>`

The `profile_vv_gql_token` cookie is set when Pedro is logged into Upwork
in the Profile-Auto Chrome instance. Mint via `cb cookies`:

```bash
cb cookies-bearer https://www.upwork.com/ profile_vv_gql_token
```

`visitor_gql_token` works for `findSkills` (read-only) but NOT for the
write mutation `updateSkillsGql` (returns 403 ExecutionAborted).

## 1 — Resolve skill names → ontology UIDs

```graphql
query searchSkillsByPrefLabel(
  $query: String!, $type: OntologyEntityType!, $status: OntologyEntityStatus!,
  $ordering: String!, $limit: Int!
) {
  ontologyElementsSearchByPrefLabel(filter: {
    preferredLabel_any: $query, type: $type, entityStatus_eq: $status,
    sortOrder: $ordering, limit: $limit
  }) {
    id
    preferredLabel
  }
}
```

Variables (per skill):
```json
{
  "query": "AI Agent Development",
  "type": "SKILL",
  "status": "ACTIVE",
  "ordering": "match-start",
  "limit": 5
}
```

Alias: `findSkills`. Already done — see `upwork-skill-uids.json`.

## 2 — Read current skill list (sanity check before write)

```graphql
query getProfileSkills($profileUrl: String) {
  talentVPDAuthProfile(filter: { profileUrl: $profileUrl }) {
    profile {
      skills {
        node {
          uid: id
          id
          name
          prettyName
          active
          rank
          description
        }
      }
    }
  }
}
```

Alias: `getProfileSkills`. Variables: `{ profileUrl: "~01dae7197e964ddf3f" }`.

## 3 — Write 20-list (the mutation breakthrough)

```graphql
mutation updateTalentProfileSkills($input: TalentProfileSkillsInput!) {
  updateTalentProfileSkills(input: $input) {
    status
  }
}
```

Variables — **payload shape is `[{skillID: <uid>}]`**, not a flat string array.
Source: `app.868bb9e3.js` line `const r=n.map(e=>({skillID:e.ontologySkill.uid}))`.

```json
{
  "input": {
    "skills": [
      {"skillID": "1031626716094119936"},
      {"skillID": "1631308909744410624"},
      {"skillID": "1733104401058775043"},
      {"skillID": "1691099314245873665"},
      {"skillID": "1691099315571273728"},
      {"skillID": "1691099315239923712"},
      {"skillID": "1691099315080540161"},
      {"skillID": "1623716864308154368"},
      {"skillID": "996364628025274386"},
      {"skillID": "996364628025274389"},
      {"skillID": "1504884906003529729"},
      {"skillID": "1031626717876699136"},
      {"skillID": "1031626730153426944"},
      {"skillID": "1031626778639581184"},
      {"skillID": "1270387306804789248"},
      {"skillID": "1691099315655159809"},
      {"skillID": "996364628000108546"},
      {"skillID": "1031626762999021568"},
      {"skillID": "1631308909400477696"},
      {"skillID": "1623716864341708800"}
    ]
  }
}
```

Alias: `updateSkillsGql`. Skill order = displayed rank (Upwork sorts by array index).

## 4 — One-shot execution

```bash
# After Pedro logs into Profile-Auto Chrome once:
TOKEN=$(cb cookies-bearer https://www.upwork.com/ profile_vv_gql_token)

# Sanity check current list
cb gql https://www.upwork.com/api/graphql/v1 \
  --alias getProfileSkills \
  --query 'query getProfileSkills($profileUrl: String) { talentVPDAuthProfile(filter:{profileUrl:$profileUrl}){profile{skills{node{id name rank}}}} }' \
  --vars '{"profileUrl":"~01dae7197e964ddf3f"}' \
  --bearer "$TOKEN"

# Write the 20-list (idempotent, replaces entire skill array)
cb gql https://www.upwork.com/api/graphql/v1 \
  --alias updateSkillsGql \
  --query 'mutation updateTalentProfileSkills($input: TalentProfileSkillsInput!) { updateTalentProfileSkills(input: $input) { status } }' \
  --vars "$(cat upwork-skill-uids.json | jq '{input:{skills:[.resolved[].id]}}')" \
  --bearer "$TOKEN"
```

## What this collapses

UPWORK-OPERATOR-CHECKLIST.md Batch 1 (5–7 minute Algolia typeahead session)
becomes 2 cb gql calls — total wall time ~3 seconds.

The whole reason the modal needed `isTrusted=true` events (Vue reactive store
gating Save button) is now bypassed: the mutation is the actual write path,
and the modal was just sugar around it.

## Gaps in the 20-list

- **Model Context Protocol** — not in Upwork ontology. Submit via "Suggest a
  skill" or replace with `Generative AI` (already substituted).
- **Playwright** — not in Upwork ontology. Replaced with `AI Chatbot`.
- **Anthropic Claude** — substituted with `Claude` (canonical UID).
- **AWS Bedrock** — substituted with `Amazon Bedrock` (canonical name).
- **pgvector** — substituted with `Vector Database` (closest ontology match).

Source: `upwork-skill-uids.json` `gaps` field.

## Same pattern unlocks

1. **Catalog tag commit** — `findSkills` for tags + `updateProjectCatalogTags` mutation (TODO: capture mutation body via same JS-grep technique).
2. **Portfolio item skills** — `addPortfolioItem`/`updatePortfolioItem` mutations include skill UIDs.
3. **Specialized profile skills** — already discovered: `updateSpecializedProfileSkills` action calls a different REST endpoint at `h` (need to capture).

The chrome-bridge `cb gql` primitive plus `cb scripting.eval` for chunk-grepping
gives a repeatable pattern for any Upwork (or sibling site) form gated on Algolia
typeahead. No `chrome.debugger` needed for any write that is GraphQL-backed.
