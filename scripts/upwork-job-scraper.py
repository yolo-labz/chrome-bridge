#!/usr/bin/env python3
"""upwork-job-scraper.py — pull live job listings from Pedro's authenticated
Upwork session via chrome-bridge, score by ROI fit, output ranked CSV+JSON.

Strategy: navigate Profile-Auto Chrome to N search URLs, read window.__NUXT__
state for each (jobs array with full client signals), dedupe by uid, score,
output.
"""

from __future__ import annotations
import csv, json, sys, time, urllib.request, uuid
from datetime import datetime, timezone
from pathlib import Path

RELAY = "http://127.0.0.1:9224"

# Pedro's 20-skill set (UID set). Used for skill_match score.
PEDRO_SKILL_UIDS = {
    "1031626716094119936",  # Artificial Intelligence
    "1631308909744410624",  # Large Language Model
    "1733104401058775043",  # Retrieval Augmented Generation
    "1691099314245873665",  # AI Agent Development
    "1691099315571273728",  # Claude
    "1691099315239923712",  # Amazon Bedrock
    "1691099315080540161",  # Vector Database
    "1623716864308154368",  # Prompt Engineering
    "996364628025274386",   # Python
    "996364628025274389",   # TypeScript
    "1504884906003529729",  # Web Scraping
    "1031626717876699136",  # Automation
    "1031626730153426944",  # Data Extraction
    "1031626778639581184",  # Selenium WebDriver
    "1270387306804789248",  # Cloud Architecture
    "1691099315655159809",  # FastAPI
    "996364628000108546",   # PostgreSQL
    "1031626762999021568",  # Node.js
    "1631308909400477696",  # Generative AI
    "1623716864341708800",  # AI Chatbot
}

# Niche keywords for description-level scoring (Pedro's positioning anchors).
NICHE_KEYWORDS_HIGH = [
    "anthropic", "claude", "mcp", "model context protocol",
    "rag", "retrieval-augmented", "retrieval augmented",
    "agentic", "ai agent", "agent loop", "langgraph",
    "bedrock", "vector database", "pgvector",
]
NICHE_KEYWORDS_MEDIUM = [
    "llm", "large language", "generative ai", "openai",
    "vector search", "semantic search", "embedding",
    "fastapi", "next.js", "postgres",
]
NICHE_KEYWORDS_COMPLIANCE = [
    "audit", "compliance", "hipaa", "gdpr", "lgpd",
    "soc2", "iso 27001", "regulated", "fintech",
    "eu ai act", "bcb", "hash chain", "rekor",
]
ANTI_KEYWORDS = [
    "wordpress", "shopify", "wix", "squarespace",
    "lead generation", "data entry only", "email scraping",
    "drop shipping", "crypto", "web3", "nft",
    "social media management", "instagram automation",
]

# Search queries per ICP cluster
SEARCH_URLS = [
    ("anthropic_claude",  "anthropic claude"),
    ("mcp_server",        "mcp server"),
    ("rag_pipeline",      "rag pipeline"),
    ("ai_agent_dev",      "ai agent development"),
    ("langgraph",         "langgraph"),
    ("bedrock_claude",    "aws bedrock claude"),
    ("claude_code",       "claude code plugin"),
    ("compliance_llm",    "compliance llm audit"),
    ("agentic_rag",       "agentic rag"),
]


def cb(kind, args, wait=60):
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


def pull_jobs_for_query(tab_id: int, q_label: str, q: str) -> list:
    """Navigate to /nx/search/jobs/?q=<q>&sort=recency, pull jobs from __NUXT__."""
    import urllib.parse
    url = f"https://www.upwork.com/nx/search/jobs/?q={urllib.parse.quote_plus(q)}&sort=recency"
    cb("tabs.update", {"tabId": tab_id, "url": url, "active": True})
    time.sleep(7)

    # Read __NUXT__ jobs
    code = r"""
(() => {
  const seen = new WeakSet();
  function findJobs(obj, depth=0) {
    if (depth > 8 || !obj || typeof obj !== 'object' || seen.has(obj)) return null;
    seen.add(obj);
    if (Array.isArray(obj)) {
      // Recognize: array of objects with both `uid` AND `ciphertext` AND `title`
      if (obj.length > 0 && obj[0] && obj[0].uid && obj[0].ciphertext && obj[0].title) return obj;
      for (const item of obj) {
        const r = findJobs(item, depth+1);
        if (r) return r;
      }
      return null;
    }
    if (obj.jobs && Array.isArray(obj.jobs) && obj.jobs.length > 0 && obj.jobs[0].uid) return obj.jobs;
    if (obj.results && Array.isArray(obj.results) && obj.results.length > 0 && obj.results[0].uid) return obj.results;
    for (const k of Object.keys(obj)) {
      const r = findJobs(obj[k], depth+1);
      if (r) return r;
    }
    return null;
  }
  const jobs = findJobs(window.__NUXT__);
  return jobs ? JSON.parse(JSON.stringify(jobs)) : [];
})()
"""
    r = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"}, wait=30)
    return r.get("result") or []


def score_job(j: dict) -> dict:
    """Compute ROI score 0-100 + sub-scores + diagnostics."""
    out = {
        "uid": j.get("uid"),
        "ciphertext": j.get("ciphertext"),
        "title": j.get("title", ""),
        "type": j.get("type"),
        "publishedOn": j.get("publishedOn"),
        "createdOn": j.get("createdOn"),
        "engagement": j.get("engagement"),
        "tier": j.get("tierText") or "",
    }

    # === Rate / amount signal ===
    rate_score = 0
    rate_value = None
    hb = j.get("hourlyBudget") or {}
    amt = j.get("amount") or {}
    if hb.get("min") or hb.get("max"):
        # Hourly job
        rate_value = float(hb.get("max") or hb.get("min") or 0)
        if rate_value >= 95:
            rate_score = 100
        elif rate_value >= 75:
            rate_score = 75
        elif rate_value >= 50:
            rate_score = 50
        elif rate_value >= 30:
            rate_score = 25
        else:
            rate_score = 5
    elif amt.get("amount"):
        # Fixed-price job
        amt_val = float(amt.get("amount") or 0)
        rate_value = amt_val
        if amt_val >= 5000:
            rate_score = 95
        elif amt_val >= 2000:
            rate_score = 80
        elif amt_val >= 1000:
            rate_score = 60
        elif amt_val >= 500:
            rate_score = 35
        elif amt_val >= 100:
            rate_score = 15
        else:
            rate_score = 5
    out["rate_value"] = rate_value
    out["rate_score"] = rate_score

    # === Client signals ===
    c = j.get("client") or {}
    client_score = 0
    total_spent = 0
    try:
        total_spent = float(c.get("totalSpent") or 0)
    except (TypeError, ValueError):
        total_spent = 0
    payment_verified = bool(c.get("isPaymentVerified"))
    total_reviews = c.get("totalReviews") or 0

    if payment_verified:
        client_score += 25
    if total_spent >= 50000:
        client_score += 40
    elif total_spent >= 10000:
        client_score += 30
    elif total_spent >= 5000:
        client_score += 20
    elif total_spent >= 1000:
        client_score += 10
    elif total_spent >= 100:
        client_score += 3
    if total_reviews >= 10:
        client_score += 20
    elif total_reviews >= 3:
        client_score += 10
    elif total_reviews >= 1:
        client_score += 5
    if c.get("location", {}).get("country") in ("United States", "United Kingdom", "Canada", "Germany", "Australia", "Switzerland", "Netherlands", "Sweden", "Norway", "Denmark"):
        client_score += 15
    out["client_score"] = min(100, client_score)
    out["payment_verified"] = payment_verified
    out["client_country"] = (c.get("location") or {}).get("country", "?")
    out["client_total_spent"] = total_spent
    out["client_reviews"] = total_reviews

    # === Skill match ===
    attrs = j.get("attrs") or []
    job_skill_uids = set(a.get("uid") for a in attrs if a.get("uid"))
    overlap = PEDRO_SKILL_UIDS & job_skill_uids
    skill_match_pct = (len(overlap) / max(1, len(job_skill_uids))) * 100 if job_skill_uids else 0
    out["skill_overlap_count"] = len(overlap)
    out["skill_overlap_pct"] = round(skill_match_pct, 1)
    out["job_skill_count"] = len(job_skill_uids)
    skill_score = min(100, len(overlap) * 25)  # 4+ overlapping skills = 100

    # === Niche keyword fit (description + title) ===
    text_l = ((j.get("title") or "") + " " + (j.get("description") or "")).lower()
    high_hits = sum(1 for k in NICHE_KEYWORDS_HIGH if k in text_l)
    med_hits = sum(1 for k in NICHE_KEYWORDS_MEDIUM if k in text_l)
    comp_hits = sum(1 for k in NICHE_KEYWORDS_COMPLIANCE if k in text_l)
    anti_hits = sum(1 for k in ANTI_KEYWORDS if k in text_l)
    niche_score = min(100, high_hits * 20 + med_hits * 8 + comp_hits * 12 - anti_hits * 30)
    niche_score = max(0, niche_score)
    out["niche_high_hits"] = high_hits
    out["niche_med_hits"] = med_hits
    out["niche_compliance_hits"] = comp_hits
    out["niche_anti_hits"] = anti_hits

    # === Freshness decay (within 24h = full, 24-72h = decay, >72h = penalize) ===
    posted = j.get("publishedOn") or j.get("createdOn")
    age_h = None
    fresh_score = 50
    if posted:
        try:
            dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if age_h < 2:
                fresh_score = 100
            elif age_h < 8:
                fresh_score = 85
            elif age_h < 24:
                fresh_score = 65
            elif age_h < 48:
                fresh_score = 40
            elif age_h < 72:
                fresh_score = 25
            else:
                fresh_score = 10
        except Exception:
            pass
    out["age_h"] = round(age_h, 1) if age_h is not None else None
    out["fresh_score"] = fresh_score

    # === Proposal volume penalty ===
    proposals = (j.get("proposalsTier") or "").upper()
    prop_score = 100
    if "5_TO_10" in proposals or "5-10" in proposals or "LESS_THAN_5" in proposals:
        prop_score = 100
    elif "10_TO_15" in proposals or "10-15" in proposals:
        prop_score = 80
    elif "15_TO_20" in proposals or "15-20" in proposals:
        prop_score = 60
    elif "20_TO_50" in proposals or "20-50" in proposals or "20+" in proposals:
        prop_score = 30
    elif "50_PLUS" in proposals or "50+" in proposals:
        prop_score = 5
    out["proposals_tier"] = j.get("proposalsTier")
    out["prop_score"] = prop_score

    # === Composite ===
    composite = (
        rate_score * 0.30 +
        out["client_score"] * 0.20 +
        skill_score * 0.15 +
        niche_score * 0.20 +
        fresh_score * 0.10 +
        prop_score * 0.05
    )
    if anti_hits >= 1:
        composite *= 0.3
    if not payment_verified:
        composite *= 0.4
    if total_spent < 1000:
        composite *= 0.7
    out["score"] = round(composite, 1)
    out["composite_components"] = {
        "rate": rate_score,
        "client": out["client_score"],
        "skill": skill_score,
        "niche": niche_score,
        "fresh": fresh_score,
        "props": prop_score,
    }

    # Build canonical URL
    if j.get("ciphertext"):
        out["url"] = f"https://www.upwork.com/jobs/{j['ciphertext'].lstrip('~')}"

    return out


def main():
    out_dir = Path("/Users/notroot/Documents/Notes/2. Areas/👷 Work/UPWORK-JOB-DATASET-2026-04-27")
    out_dir.mkdir(parents=True, exist_ok=True)

    tab = cb("tabs.query", {"query": {}})["tabs"][0]
    tab_id = tab["id"]

    # Pull from each search query
    by_uid = {}  # uid -> {raw: dict, queries: set}
    for q_label, q in SEARCH_URLS:
        print(f"\n=== {q_label} ({q!r}) ===")
        jobs = pull_jobs_for_query(tab_id, q_label, q)
        print(f"  {len(jobs)} jobs")
        for j in jobs:
            uid = j.get("uid")
            if not uid:
                continue
            if uid not in by_uid:
                by_uid[uid] = {"raw": j, "queries": set()}
            by_uid[uid]["queries"].add(q_label)

    print(f"\n=== Aggregated unique jobs: {len(by_uid)} ===")

    # Score everything
    scored = []
    for uid, entry in by_uid.items():
        s = score_job(entry["raw"])
        s["matched_queries"] = sorted(entry["queries"])
        scored.append(s)

    scored.sort(key=lambda x: x["score"], reverse=True)

    # Persist raw JSON dataset
    raw_dataset = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "captured_at_brt": time.strftime("%d/%m/%Y %H:%M BRT", time.localtime()),
        "queries": [(l, q) for l, q in SEARCH_URLS],
        "total_unique": len(by_uid),
        "scored": scored,
        "raw_by_uid": {uid: entry["raw"] for uid, entry in by_uid.items()},
    }
    raw_path = out_dir / "03-job-dataset-raw.json"
    raw_path.write_text(json.dumps(raw_dataset, indent=2, ensure_ascii=False, default=str))
    print(f"raw dataset → {raw_path}")

    # CSV ranked
    csv_path = out_dir / "03-job-dataset-ranked.csv"
    fields = [
        "score", "rate_value", "rate_score", "type", "engagement", "title",
        "client_country", "payment_verified", "client_total_spent", "client_reviews",
        "skill_overlap_count", "skill_overlap_pct", "job_skill_count",
        "niche_high_hits", "niche_med_hits", "niche_compliance_hits", "niche_anti_hits",
        "fresh_score", "age_h", "proposals_tier", "prop_score",
        "tier", "matched_queries", "url",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for s in scored:
            row = {k: s.get(k) for k in fields}
            row["matched_queries"] = ",".join(s.get("matched_queries") or [])
            w.writerow(row)
    print(f"ranked CSV → {csv_path}")

    # Print top 20 to stdout
    print(f"\n=== TOP 20 ===")
    for i, s in enumerate(scored[:20], 1):
        rate = f"${s.get('rate_value','?')}"
        print(f"{i:2}. score={s['score']:5.1f}  rate={rate:>8}  type={s.get('type','?')}  {s.get('title','')[:65]}")
        print(f"      client={s.get('client_country','?')[:15]} ${s.get('client_total_spent','?')} verified={s.get('payment_verified')} skills={s.get('skill_overlap_count')}/{s.get('job_skill_count')} niche=H{s.get('niche_high_hits')}/M{s.get('niche_med_hits')}/C{s.get('niche_compliance_hits')} anti={s.get('niche_anti_hits')} age={s.get('age_h')}h props={s.get('proposals_tier')}")
        print(f"      {s.get('url','')}")
        print(f"      queries: {','.join(s.get('matched_queries') or [])}")


if __name__ == "__main__":
    main()
