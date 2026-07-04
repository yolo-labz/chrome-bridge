#!/usr/bin/env python3
"""upwork-watch-proposals.py — poll Upwork for proposal status changes.

For each proposal ID, fetches:
  - validateUpdateOnJobApplication[ClientViewed, Expired]  → has client opened it?
  - supplierInitiatedInitialMessage(proposalId)            → has client/Pedro messaged?
  - proposalRoomId(proposalId)                             → chat room for direct DM

Output: state JSON + delta-since-last-run notification (if reply / view).

Auth: page-context fetch from logged-in Profile-Auto Chrome (subordinate
oauth scope auto-attached by Upwork SPA).

Usage:
  upwork-watch-proposals.py [--once | --watch-every Ns]
"""

from __future__ import annotations
import argparse, json, sys, time, urllib.parse, urllib.request, uuid, hashlib
from pathlib import Path
from datetime import datetime, timezone

RELAY = "http://127.0.0.1:9224"
STATE_PATH = Path.home() / ".local/state/chrome-bridge/upwork-proposal-watch.json"

# 4 proposals sent today + add older ones if you want to track them
WATCHED_PROPOSALS = [
    {"id": "2048868130120708097", "label": "1-contract-processing", "fired_at": "2026-04-27T17:30+00:00"},
    {"id": "2048868832265654273", "label": "2-langgraph-multi-agent", "fired_at": "2026-04-27T17:35+00:00"},
    {"id": "2048868628103315457", "label": "4-rag-uk", "fired_at": "2026-04-27T17:33+00:00"},
    {"id": "2048867183690911745", "label": "5-mcp-fub", "fired_at": "2026-04-27T17:25+00:00"},
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


def page_fetch(tab_id, alias, query, variables) -> dict:
    """Page-context fetch with auto-attached subordinate-oauth bearer."""
    code = """
    (async (alias, query, vars) => {
      const tok = document.cookie.match(/profile_vv_gql_token=([^;]+)/)?.[1];
      const xsrf = document.cookie.match(/XSRF-TOKEN=([^;]+)/)?.[1];
      const r = await fetch('/api/graphql/v1?alias=' + encodeURIComponent(alias), {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          ...(tok ? {'Authorization': 'Bearer ' + tok} : {}),
          ...(xsrf ? {'X-XSRF-TOKEN': decodeURIComponent(xsrf)} : {}),
        },
        body: JSON.stringify({ query, variables: vars }),
      });
      try {
        return { status: r.status, data: (await r.json()) };
      } catch (e) {
        return { status: r.status, err: String(e) };
      }
    })(arguments[0], arguments[1], arguments[2])
    """.replace("arguments[0]", json.dumps(alias)).replace("arguments[1]", json.dumps(query)).replace("arguments[2]", json.dumps(variables))
    return cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"}, wait=30).get("result") or {}


def check_proposal(tab_id, proposal_id):
    """Returns dict with viewed (bool), expired (bool), msg_count (int), room_id (str)."""
    state = {"id": proposal_id}

    # 1. ClientViewed + Expired flags
    r = page_fetch(tab_id, "validateUpdateOnJobApplication", """
        mutation validateUpdateOnJobApplication($input: VJApplicationUpdateRequestInput!) {
          validateUpdateOnJobApplication(input: $input) {
            valid
            results { type passed failureMessage }
          }
        }
    """, {"input": {"validations": ["ClientViewed", "Expired"], "applicationId": proposal_id}})
    results = ((r.get("data") or {}).get("data") or {}).get("validateUpdateOnJobApplication", {}).get("results") or []
    for res in results:
        if res.get("type") == "ClientViewed":
            state["client_viewed"] = bool(res.get("passed"))
        if res.get("type") == "Expired":
            state["expired"] = bool(res.get("passed"))

    # 2. Initial message from client
    r = page_fetch(tab_id, "supplierInitiatedInitialMessage", """
        query supplierInitiatedInitialMessage($proposalId: ID!) {
          supplierInitiatedInitialMessage(proposalId: $proposalId) {
            totalCount
            edges {
              node { id createdDateTime message }
            }
          }
        }
    """, {"proposalId": proposal_id})
    msg = ((r.get("data") or {}).get("data") or {}).get("supplierInitiatedInitialMessage") or {}
    state["msg_count"] = msg.get("totalCount") or 0
    state["latest_msg_at"] = None
    if msg.get("edges"):
        latest = msg["edges"][-1].get("node") or {}
        state["latest_msg_at"] = latest.get("createdDateTime")
        state["latest_msg_preview"] = (latest.get("message") or "")[:200]

    # 3. Room ID for direct DM
    r = page_fetch(tab_id, "proposalRoomId", """
        query ($proposalId: ID!) {
          proposalRoomId(proposalId: $proposalId)
        }
    """, {"proposalId": proposal_id})
    state["room_id"] = ((r.get("data") or {}).get("data") or {}).get("proposalRoomId")
    return state


def check_room_for_messages(tab_id, room_id):
    """Pull messages for a proposal's chat room. Filter to client-sent only."""
    if not room_id:
        return {"messages": []}
    r = page_fetch(tab_id, "roomStories", """
        query roomStories($roomId: ID!, $first: Int) {
          roomStories(filter: {roomId_eq: $roomId, first: $first}) {
            totalCount
            edges {
              node {
                id
                createdDateTime
                message
                createdBy { id firstName lastName }
                actionType
              }
            }
          }
        }
    """, {"roomId": room_id, "first": 50})
    edges = (((r.get("data") or {}).get("data") or {}).get("roomStories") or {}).get("edges") or []
    return {"messages": [e.get("node") for e in edges if e]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--watch-every", type=int, default=0, help="Re-poll every N seconds")
    args = ap.parse_args()

    tabs = cb("tabs.query", {"query": {}})["tabs"]
    def _is_upwork(url: str) -> bool:
        # Hostname match, not substring — "evil.com/upwork.com" must not qualify
        # (py/incomplete-url-substring-sanitization).
        host = urllib.parse.urlparse(url).hostname or ""
        return host == "upwork.com" or host.endswith(".upwork.com")

    upwork_tab = next((t for t in tabs if _is_upwork(t.get("url") or "")), tabs[0])
    tab_id = upwork_tab["id"]

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prior = {}
    if STATE_PATH.exists():
        try: prior = json.loads(STATE_PATH.read_text())
        except Exception: pass

    while True:
        now = datetime.now(timezone.utc).isoformat()
        print(f"\n=== watch run @ {now} ===")
        new_state = {"checked_at": now, "proposals": {}}
        for p in WATCHED_PROPOSALS:
            print(f"\n  [{p['label']}] id={p['id']}")
            s = check_proposal(tab_id, p["id"])
            new_state["proposals"][p["id"]] = s
            print(f"    viewed={s.get('client_viewed')} expired={s.get('expired')} msgs={s.get('msg_count')}")
            if s.get("latest_msg_at"):
                print(f"    latest_msg: {s.get('latest_msg_at')}")
                print(f"      preview: {s.get('latest_msg_preview','')[:120]}")
            # Diff against prior
            old = (prior.get("proposals") or {}).get(p["id"]) or {}
            if old:
                if s.get("client_viewed") and not old.get("client_viewed"):
                    print(f"    🆕 NEW: client viewed proposal!")
                if (s.get("msg_count") or 0) > (old.get("msg_count") or 0):
                    print(f"    🆕 NEW MESSAGE — {s.get('msg_count')} vs prior {old.get('msg_count')}")
        STATE_PATH.write_text(json.dumps(new_state, indent=2, ensure_ascii=False))
        print(f"\n  state → {STATE_PATH}")

        if args.once or args.watch_every == 0:
            break
        prior = new_state
        time.sleep(args.watch_every)


if __name__ == "__main__":
    main()
