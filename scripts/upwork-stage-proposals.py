#!/usr/bin/env python3
"""upwork-stage-proposals.py — stage top N Upwork proposals in parallel tabs.

For each top pick:
  1. Open new Chrome tab to /nx/proposals/job/<ct>/apply/
  2. Wait for form to load
  3. Fill milestone description + amount (fixed-price) OR rate (hourly)
  4. Set cover letter via native HTMLTextAreaElement value setter + input event
  5. Leave Send button UNCLICKED — Pedro reviews + clicks manually

All tailored cover letters live in this file (edit before running to tweak).

Usage:
  upwork-stage-proposals.py [pick-number...]   # default: stage all in PROPOSALS list
"""

from __future__ import annotations
import json, sys, time, urllib.request, uuid

RELAY = "http://127.0.0.1:9224"

# Top 6 picks per 04-roi-synthesis-and-action-list.md + dataset refresh
PROPOSALS = [
    {
        "label": "1-contract-processing",
        "ciphertext": "~022048853726094937041",
        "type": "fixed",
        "milestone_desc": "Phase 1 — POC across 3 contract types, 50 documents, source-anchored extraction + classification + summarization",
        "milestone_amount": "500",
        "cover_letter": """Contract-processing for non-technical teams in 2026 has three failure modes I'd plan around:

1. OCR drift — Textract vs DocAI behave very differently on scanned vs born-digital. A unified chunking layer with page+span anchors makes every extracted field carry provenance.
2. Classification confidence not surfaced — model thinks NDA, it's actually MSA, no audit trail. Confidence scores route to a manual-review queue, not silently store.
3. Field extraction without source-anchor — parties shown but not "from page 4 line 12". Buyers can't trust answers they can't trace.

For your scope I'd ship:
- Document pipeline: AWS Textract (scanned + handwriting) + native parser (born-digital PDFs + Word) → unified chunking with (page, span) anchors
- Classification: Claude Haiku two-pass triage + Sonnet on uncertain (~$0.04/doc avg)
- Field extraction: structured-output via Claude tool-use — every field carries source-anchor metadata
- Storage: single Postgres with pgvector + ParadeDB BM25 — searchable + ACID, no separate vector DB tax
- Plain-English summaries: separate prompt with cost ceiling per doc

Recent reference: shipped a similar three-tier AI document processor (Haiku triage → Sonnet extract → Opus ambiguous), JSONB storage, FastAPI + Next.js dashboard. Pattern-transferable.

The $500 budget covers a phase-1 POC scope (3 contract types, 50 docs, single user). Phase-2 production hardening priced after sign-off — no surprises.

Two scope clarifiers:
1. Document volume — hundreds, thousands, or higher?
2. Existing cloud — AWS / GCP / Azure / on-prem?

— Pedro""",
    },
    {
        "label": "2-langgraph-multi-agent",
        "ciphertext": "~022048822373020540885",
        "type": "fixed",
        "milestone_desc": "Phase 1 — LangGraph workflow + decision-routing logic + RAG pipeline POC with 1 vector DB integration + scenario tests",
        "milestone_amount": "100",
        "cover_letter": """Multi-agent LangGraph workflows in 2026 split cleanly into three buckets: (1) sequential-decision (router → specialist → reviewer), (2) parallel-fan-out (N specialists vote), (3) iterative-refinement (judge loop). Yours reads like (1) given "decision-making chatbot, query routing, intermediate operations".

Three places these workflows usually break past the demo:
- Tool-call retries without context-budget caps — one runaway loop blows $50 in tokens before anyone notices
- No state-machine timeout — agent loops indefinitely on ambiguous input
- HITL escalation node added too late (better designed as nodes 1-2 of the graph, not a recovery patch)

For your scope:
- LangGraph state machine with explicit timeout + cost-ceiling per node
- Router: Claude Sonnet (decision quality matters), specialists: Haiku (60-80% cost reduction)
- Multi-vector-DB integration: pgvector single-Postgres OR Pinecone — depends on tenant model + scale
- Decision-trace ledger keyed on (prompt_v, doc_ids, model_v, output_hash) — makes regression tests trivial
- Performance/accuracy harness with 20+ canonical scenarios before deploy

Reference build: production Claude agent with p95 4.2s, 0.4% loop-divergence, $0.12/successful-task gateway cost.

The $100 budget covers a phase-1 POC (workflow skeleton + 1 vector DB + 5-scenario test). Phase-2 production hardening (additional vector DBs, observability, retry budgets) priced after sign-off.

Two scope clarifiers:
1. Bedrock or first-party Anthropic API?
2. Which vector DB is the primary — Pinecone, Chroma, Weaviate, Qdrant, FAISS?

— Pedro""",
    },
    {
        "label": "3-hipaa-telehealth",
        "ciphertext": "~022047354934614141592",
        "type": "hourly",
        "hourly_rate": "95",
        "cover_letter": """HIPAA-grade agentic loops in 2026 have three failure modes that bite past the demo: (1) memory ON by default making RTBF impossible, (2) PHI in tool-call args bypassing your audit log, (3) decision-trace ledger living in the product DB instead of an append-only signed plane.

For tele-health agentic work — Embeddables automation + Lead Intake + the 80%-to-final-page pattern — I'd land on:
- LangGraph state machine with explicit human-review escalation at the "click submit" node (HITL is non-optional under HIPAA breach-notification timelines)
- MCP tool boundary as the audit perimeter — every Embeddables-builder tool call signed + logged before the agent gets to mutate state
- Hash-chained decision-trace per tenant: (request_id, prompt_hash, retrieved_doc_hashes, model_id+v, output_hash) — drops into HIPAA security review without a separate audit pipeline
- Inference perimeter: AWS Bedrock region-pinned (HIPAA-eligible) or strictly first-party Anthropic with BAA — depends on existing AWS posture
- Lead-intake agent: Claude Sonnet for EDE-fill reasoning + Haiku for field extraction; "weird edge cases" surface with explicit reason annotations to the human queue

Recent: shipped a compliance-grade RAG architecture writeup for tier-1 LATAM banking with this exact audit-plane pattern. Public writeup at blog.home301server.com.br.

Rate $95/hr ongoing. First week scoping the three agents in a kickoff doc + sequencing the build order.

Two clarifiers before quoting:
1. Existing AWS account with Bedrock enabled + BAA, or build from scratch?
2. Audit retention — 6 years (HIPAA floor) or longer per state mandate?

— Pedro""",
    },
    {
        "label": "4-rag-uk",
        "ciphertext": "~022048752388526963290",
        "type": "fixed",
        "milestone_desc": "Phase 1 — RAG pipeline POC: ingestion + chunking + pgvector + retrieval API + basic embedded widget",
        "milestone_amount": "200",
        "cover_letter": """The "AI chatbot with RAG embedded on a website" pattern in 2026 is mostly an orchestration problem, not a model problem. Three things that usually break past the POC:

- No reranker tier — embedding similarity alone gives 60-70% recall@5; adding cross-encoder rerank (Cohere or BGE) pushes to 80-85% at ~5x lower cost than agentic RAG
- Vector DB as separate service — breaks ACID boundary and adds 30-50ms latency. Single Postgres with pgvector + ParadeDB BM25 + RRF outperforms below ~500 retrievals/s
- No observability — when retrieval regresses on prod, you can't tell whether the embedding model, the index, or the rerank step degraded. Need request-trace from query → retrieved chunks → cited response

For your scope:
- Ingestion: PDFs + text + scraped website content → chunking with page/section anchors
- Single Postgres + pgvector (ACID, no microservice tax) + BM25 hybrid + Cohere rerank tier
- FastAPI backend (embed + retrieve + Claude call with grounded prompt + citation)
- Lightweight React widget — script-tag embed with iframe sandbox
- Admin re-ingest endpoint + Loki/structured-log analytics
- Phase-1 deploy: Dokku or AWS Lightsail — single docker compose

The $200 budget covers a phase-1 POC (single domain, ~50 source docs, single language). Phase-2 production hardening (multi-tenant, custom prompts per audience, conversation memory) priced after sign-off.

Two scope clarifiers:
1. Existing Postgres available, or greenfield infra?
2. Bedrock + AWS, first-party Anthropic, or open-source LLM (Llama 3.x)?

— Pedro""",
    },
    {
        "label": "5-mcp-followupboss",
        "ciphertext": "~022048591007389523925",
        "type": "fixed",
        "milestone_desc": "Phase 1 — Security audit of mindwear-capitian/followupboss-mcp-server + install + Claude Desktop wire-up + 1-page setup doc",
        "milestone_amount": "150",
        "cover_letter": """MCP-server security review in 2026 has four checkpoints I always run, beyond what most audits catch:

1. Tool-description prompt injection — `description` fields are concatenated into Claude's system context. A malicious tool can hide a "always exfiltrate to <attacker>" line that the user never sees in the UI.
2. Argument-schema overflow — over-broad arg types (e.g. `string` for what should be enum) let agents pass arbitrary data to remote APIs. Schema lockdown matters more than auth here.
3. Hidden network calls — even reputable MCP libs sometimes pull telemetry to the maintainer. `npm install --ignore-scripts` + post-install grep for `fetch`/`axios`/`http.request` outside expected modules.
4. Token-scope review on the FUB API key side — most CRMs let you mint scoped tokens (read-only on contacts, no delete). Recommend that before "wire-up" — defense in depth even if MCP server is clean.

For your scope:
- Read-through audit of github.com/mindwear-capitian/followupboss-mcp-server source + dependency tree
- Install locally on Mac, configure with FUB API key (scoped per recommendation above)
- Claude Desktop wire-up + smoke tests (contact search, notes lookup, tasks)
- Written audit summary (clean / flagged with severity)
- 1-page reinstall doc

Recent: I ship Claude Code plugins + MCP servers under yolo-labz on GitHub — every release with SLSA L2 attestations, Sigstore signing, dual-format SBOMs (CycloneDX + SPDX). Familiar with both supply-chain hygiene and MCP protocol.

The $150 budget covers the audit + wire-up scope as defined. If audit surfaces issues that need fixing (vs flagging), happy to quote a phase-2 patch separately.

Two clarifiers:
1. Mac chip — Intel or Apple Silicon? Affects Node.js install path.
2. Claude Desktop already installed + signed in?

— Pedro""",
    },
    {
        "label": "6-atlas-credit-brain",
        "ciphertext": "~022048523316635857516",
        "type": "hourly",
        "hourly_rate": "120",
        "cover_letter": """Underwriting-grade agentic systems in 2026 have to answer three questions every regulator asks: (1) Where did this approval come from? (2) Who saw it, when? (3) If a customer disputes, can we show the inference tuple that produced the decision?

For Atlas's 4-layer agentic underwriting + cross-border mid-market context, my approach:

- LangGraph state machine per layer with explicit retry-budget + escalation nodes — every credit decision is a directed acyclic graph of evidence + reasoning steps
- Single-Postgres retrieval (pgvector + ParadeDB BM25 + RRF + cross-encoder rerank) — no separate vector microservice; ACID boundary survives multi-tenant + warehouse-lender isolation
- Signed inference tuples per request: (prompt_hash, retrieved_doc_hashes, model_id+v, output_hash) — drops into ECOA/Reg-B audit packs and warehouse-lender due diligence reviews
- Hash-chained decision-trace per tenant, hourly Merkle batch anchored to public transparency log (Rekor) — proves no after-the-fact tampering
- Inference perimeter: AWS Bedrock region-pinned for SOC2 + BCB 4.893 alignment, or first-party Anthropic with explicit DPA — Atlas's cross-border posture probably benefits from regional Bedrock for data residency
- Cost-ceiling at the agent loop level (not per-call) — runaway agentic loops in underwriting can rack up four-digit token costs in minutes; need circuit-breakers tied to the per-decision budget

Recent: public writeup on compliance-grade RAG for tier-1 LATAM banking applying this exact audit-plane pattern. Forced-citation prompting drops hallucinated decisions to ~zero, p95 retrieval 180ms, audit-log overhead 7ms. blog.home301server.com.br.

Rate $120/hr. Phase-1 architecture sprint (40h fixed) recommended over open-ended hourly to start — quote on confirmation. Builds the four-layer skeleton + decision-trace ledger + 2 reference underwriting flows.

Two clarifiers:
1. Underwriting product split — what's the % between consumer-credit, BNPL, factoring, and commercial?
2. Existing audit-log infra (Datadog/Splunk) you want to integrate with, or build from scratch?

— Pedro""",
    },
]


def cb(kind, args, wait=180):
    jid = uuid.uuid4().hex
    body = json.dumps({"id": jid, "kind": kind, "args": args}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"{RELAY}/job", data=body, headers={"Content-Type": "application/json"}, method="POST",
    ), timeout=10).read()
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f"{RELAY}/await/{jid}?wait=20", timeout=25)
            raw = r.read()
            if raw:
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code != 204:
                return {"ok": False, "error": f"http {e.code}"}
    return {"ok": False, "error": "timeout"}


def stage_proposal(p, idx):
    print(f"\n=== [{idx+1}] {p['label']} ({p['ciphertext']}) ===")

    apply_url = f"https://www.upwork.com/nx/proposals/job/{p['ciphertext']}/apply/"

    # Open in NEW tab (not current — preserve other tabs Pedro might be reviewing)
    r = cb("tabs.create", {"url": apply_url, "active": False})
    if not r.get("ok"):
        print(f"  ! tab create failed: {r}")
        return False
    tab_id = r["tab"]["id"]
    print(f"  tab id={tab_id}")

    # Wait for page
    time.sleep(8)

    # Set cover letter via native setter (preserves newlines)
    code = """
    (() => {
      const tas = Array.from(document.querySelectorAll('textarea'));
      let target = null;
      for (const ta of tas) {
        let p = ta.parentElement;
        for (let n=0; n<4 && p; n++) {
          if (p.textContent.toLowerCase().includes('cover letter')) { target = ta; break; }
          p = p.parentElement;
        }
        if (target) break;
      }
      if (!target) return { err: 'no textarea' };
      const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(target, __VALUE__);
      target.dispatchEvent(new Event('input', { bubbles: true }));
      target.dispatchEvent(new Event('change', { bubbles: true }));
      return { len: target.value.length };
    })()
    """.replace("__VALUE__", json.dumps(p["cover_letter"]))
    r = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"}, wait=30)
    print(f"  cover letter: {r.get('result')}")

    # Fixed-price: fill milestone via native setter (text+amount)
    if p["type"] == "fixed":
        code = """
        (() => {
          const desc = document.querySelector('input[aria-label="Description 1"]');
          const amt = document.querySelector('input[id="milestone-amount-1"]');
          if (!desc || !amt) return { err: 'no milestone fields' };
          const setterIn = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setterIn.call(desc, __DESC__);
          desc.dispatchEvent(new Event('input', { bubbles: true }));
          setterIn.call(amt, __AMT__);
          amt.dispatchEvent(new Event('input', { bubbles: true }));
          return { desc_val: desc.value, amt_val: amt.value };
        })()
        """.replace("__DESC__", json.dumps(p["milestone_desc"])).replace("__AMT__", json.dumps(p["milestone_amount"]))
        r = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"}, wait=15)
        print(f"  milestone: {r.get('result')}")
    elif p["type"] == "hourly":
        # Hourly job — set rate input
        code = """
        (() => {
          const charged = document.querySelector('input[id="charged-amount-id"]');
          if (!charged) return { err: 'no rate input' };
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(charged, __RATE__);
          charged.dispatchEvent(new Event('input', { bubbles: true }));
          return { charged_val: charged.value };
        })()
        """.replace("__RATE__", json.dumps(p["hourly_rate"]))
        r = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"}, wait=15)
        print(f"  hourly rate: {r.get('result')}")

    # Surface Send button location for Pedro
    r = cb("scripting.eval", {"tabId": tab_id, "code": """
    (() => {
      const send = Array.from(document.querySelectorAll('button')).find(b => /^Send for/i.test(b.textContent || ''));
      if (!send) return { err: 'no send' };
      send.scrollIntoView({block: 'center'});
      const r = send.getBoundingClientRect();
      return { send_label: send.textContent.trim(), disabled: send.disabled, x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2) };
    })()
    """, "world": "MAIN"}, wait=15)
    print(f"  send: {r.get('result')}")
    return True


def main():
    indices_arg = [int(a) - 1 for a in sys.argv[1:]] if len(sys.argv) > 1 else list(range(len(PROPOSALS)))
    for i in indices_arg:
        if 0 <= i < len(PROPOSALS):
            stage_proposal(PROPOSALS[i], i)


if __name__ == "__main__":
    main()
