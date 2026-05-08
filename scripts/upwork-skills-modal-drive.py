#!/usr/bin/env python3
"""upwork-skills-modal-drive.py — drive Pedro's Upwork Skills modal to the 20-list.

Uses chrome-bridge primitives (cb gql / cb cookies / cb scripting.eval / cb
debugger.click / cb debugger.type) against a logged-in Profile-Auto Chrome.

Strategy: the legacy `updateTalentProfileSkills` GraphQL mutation silently
no-ops pre-28/05/2026 (Upwork specialized-profiles deprecation). The actual
production save fires through the modal Save button via Vue/migration-aware
internals we don't replicate. So we drive the MODAL itself with trusted
chrome.debugger Input events.

Flow:
  1. Read auth state — current skill ID set
  2. Diff against TARGET list, compute add[], remove[]
  3. For each remove: click Remove <name> Tag button
  4. For each add: type name + click first suggestion + click Clear Input
  5. Click Save
  6. Re-read auth state, verify diff applied

Pre-req: Profile-Auto Chrome (CfT 145) running with chrome-bridge extension
loaded; Pedro logged into Upwork.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

RELAY = "http://127.0.0.1:9224"
PROFILE_URL = "~01dae7197e964ddf3f"
PROFILE_PAGE = "https://www.upwork.com/freelancers/~01dae7197e964ddf3f"
GQL_ENDPOINT = "https://www.upwork.com/api/graphql/v1"


def cb(kind, args, wait=30):
    jid = uuid.uuid4().hex
    body = json.dumps({"id": jid, "kind": kind, "args": args}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"{RELAY}/job", data=body, headers={"Content-Type": "application/json"}, method="POST",
    ), timeout=10).read()
    r = urllib.request.urlopen(f"{RELAY}/await/{jid}?wait={wait}", timeout=wait + 5)
    return json.loads(r.read())


def get_skills(token, profile_url=PROFILE_URL):
    r = cb("gql", {
        "url": GQL_ENDPOINT,
        "alias": "getProfileSkills",
        "query": "query getProfileSkills($profileUrl: String) { talentVPDAuthProfile(filter:{profileUrl:$profileUrl}){profile{skills{node{id name rank}}}} }",
        "variables": {"profileUrl": profile_url},
        "bearer": token,
    })
    return [
        s.get("node") or {}
        for s in ((r.get("json") or {}).get("data", {}) or {}).get("talentVPDAuthProfile", {}).get("profile", {}).get("skills", [])
        if s
    ]


def open_skills_modal():
    """Navigate to profile + click Edit Skills. Return True if modal open."""
    tab = cb("tabs.query", {"query": {}})["tabs"][0]
    cb("tabs.update", {"tabId": tab["id"], "url": PROFILE_PAGE, "active": True})
    time.sleep(5)

    # Scroll edit btn into view
    coords = cb("scripting.eval", {"tabId": tab["id"], "code": """
(() => {
  const btn = document.querySelector('[aria-label="Edit skills"]');
  if (!btn) return null;
  btn.scrollIntoView({block:'center', behavior:'instant'});
  const r = btn.getBoundingClientRect();
  return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
})()
""", "world": "MAIN"})["result"]
    if not coords:
        print("ERROR: Edit Skills button not found (Pedro logged in?)", file=sys.stderr)
        return None

    cb("debugger.click", {"tabId": tab["id"], "x": coords["x"], "y": coords["y"]})
    time.sleep(4)

    # Verify modal opened
    open_check = cb("scripting.eval", {"tabId": tab["id"], "code": """
(() => !!document.querySelector('[role="dialog"] input[placeholder*="kill"]'))()
""", "world": "MAIN"})["result"]
    return tab["id"] if open_check else None


def remove_chip(tab_id, label):
    """Click the 'Remove <label> Tag' button. Returns True on success."""
    coords = cb("scripting.eval", {"tabId": tab_id, "code": f"""
(() => {{
  const btn = Array.from(document.querySelectorAll('[role="dialog"] button'))
    .find(b => b.textContent.trim() === 'Remove {label} Tag' || (b.getAttribute('aria-label') || '').trim() === 'Remove {label} Tag');
  if (!btn) return null;
  btn.scrollIntoView({{block:'nearest'}});
  const r = btn.getBoundingClientRect();
  return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
}})()
""", "world": "MAIN"})["result"]
    if not coords:
        print(f"  ! could not locate Remove {label!r} button")
        return False
    cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
    time.sleep(0.6)
    return True


def add_skill(tab_id, name):
    """Focus typeahead, type name, wait, click first matching suggestion, clear input."""
    inp = cb("scripting.eval", {"tabId": tab_id, "code": """
(() => {
  const i = document.querySelector('[role="dialog"] input[placeholder*="kill"]');
  if (!i) return null;
  i.focus();
  i.scrollIntoView({block:'nearest'});
  const r = i.getBoundingClientRect();
  return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
})()
""", "world": "MAIN"})["result"]
    if not inp:
        print("  ! typeahead input not found")
        return False
    cb("debugger.click", {"tabId": tab_id, "x": inp["x"], "y": inp["y"]})
    time.sleep(0.4)

    cb("debugger.type", {"tabId": tab_id, "text": name})
    time.sleep(2.0)

    # Click first suggestion that EXACTLY matches `name` (case-insensitive)
    coords = cb("scripting.eval", {"tabId": tab_id, "code": f"""
(() => {{
  // Walk DOM; suggestions are LI children of OL.air3-sortable-list NOT YET added,
  // but Algolia's dropdown uses different markup. Most reliable: any leaf-element
  // with exact text match.
  const target = {json.dumps(name)};
  const all = Array.from(document.querySelectorAll('[role="dialog"] *'));
  const matches = all.filter(e => {{
    const t = (e.textContent || '').trim();
    return t.toLowerCase() === target.toLowerCase() && e.children.length === 0;
  }});
  // Pick the one that's NOT already a chip (chips live inside OL.air3-sortable-list)
  const fresh = matches.filter(e => !e.closest('ol.air3-sortable-list'));
  const pick = fresh[0] || matches[0];
  if (!pick) return null;
  const r = pick.getBoundingClientRect();
  return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
}})()
""", "world": "MAIN"})["result"]
    if not coords:
        print(f"  ! suggestion {name!r} not found (skill may not be in Upwork ontology)")
        # Clear input via Clear Input button to recover
        clear_input(tab_id)
        return False
    cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
    time.sleep(0.8)
    clear_input(tab_id)
    return True


def clear_input(tab_id):
    """Click 'Clear Input' button to empty the typeahead."""
    coords = cb("scripting.eval", {"tabId": tab_id, "code": """
(() => {
  const btn = Array.from(document.querySelectorAll('[role="dialog"] button'))
    .find(b => /^Clear Input$/.test(b.textContent.trim()) || (b.getAttribute('aria-label') || '') === 'Clear Input');
  if (!btn) return null;
  const r = btn.getBoundingClientRect();
  return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
})()
""", "world": "MAIN"})["result"]
    if coords:
        cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
        time.sleep(0.3)


def click_save(tab_id):
    coords = cb("scripting.eval", {"tabId": tab_id, "code": """
(() => {
  const btn = Array.from(document.querySelectorAll('[role="dialog"] button'))
    .find(b => /^Save$/.test(b.textContent.trim()) && !b.disabled);
  if (!btn) return null;
  const r = btn.getBoundingClientRect();
  return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
})()
""", "world": "MAIN"})["result"]
    if not coords:
        print("ERROR: Save button not enabled (input non-empty? max-skills exceeded?)", file=sys.stderr)
        return False
    cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
    time.sleep(4)
    return True


def main():
    here = Path(__file__).resolve().parent.parent
    uids_file = here / "captures/upwork-skill-uids.json"
    uids = json.loads(uids_file.read_text())
    target_ids = {s["id"]: s["label"] for s in uids["resolved"]}
    target_labels = [s["label"] for s in uids["resolved"]]

    token_r = cb("cookies", {"url": "https://www.upwork.com/", "name": "profile_vv_gql_token"})
    cs = token_r.get("cookies") or []
    if not cs or not cs[0]:
        print("ERROR: profile_vv_gql_token not in Profile-Auto cookies. Pedro logged in?", file=sys.stderr)
        sys.exit(2)
    token = cs[0]["value"]

    print("[1/5] reading current auth state...")
    current = get_skills(token)
    current_ids = {s["id"] for s in current}
    print(f"      currently {len(current)} skills")

    target_ids_set = set(target_ids.keys())
    to_add = list(target_ids_set - current_ids)         # IDs in target not in current
    to_remove = list(current_ids - target_ids_set)      # IDs in current not in target
    print(f"      to add: {len(to_add)}, to remove: {len(to_remove)}")

    # Convert remove IDs to labels (for the modal button text)
    name_by_id = {s["id"]: s["name"] for s in current}
    label_map = {
        "python": "Python", "typescript": "TypeScript",
        "amazon-web-services": "Amazon Web Services", "docker": "Docker",
        "terraform": "Terraform", "machine-learning": "Machine Learning",
        "cloud-architecture": "Cloud Architecture", "api-development": "API Development",
        "devops": "DevOps", "data-extraction": "Data Extraction",
        "automation": "Automation", "next.js": "Next.js", "react-js": "React",
        "node.js": "Node.js", "selenium-webdriver": "Selenium WebDriver",
    }
    remove_labels = []
    for sid in to_remove:
        slug = name_by_id.get(sid)
        if slug and slug in label_map:
            remove_labels.append(label_map[slug])
        elif slug:
            remove_labels.append(slug.replace("-", " ").title())
    add_labels = [target_ids[i] for i in to_add]

    print(f"\n      remove labels: {remove_labels}")
    print(f"      add labels: {add_labels}")

    print("\n[2/5] opening Skills modal...")
    tab_id = open_skills_modal()
    if not tab_id:
        sys.exit(3)
    print("      modal open")

    print(f"\n[3/5] removing {len(remove_labels)} chips...")
    for lbl in remove_labels:
        ok = remove_chip(tab_id, lbl)
        print(f"      {'✓' if ok else '✗'} {lbl}")

    print(f"\n[4/5] adding {len(add_labels)} skills...")
    for lbl in add_labels:
        ok = add_skill(tab_id, lbl)
        print(f"      {'✓' if ok else '✗'} {lbl}")

    print("\n[4.5/5] clearing input + clicking Save...")
    clear_input(tab_id)
    time.sleep(0.4)
    if not click_save(tab_id):
        print("ABORT: Save not clickable.", file=sys.stderr)
        sys.exit(4)
    print("      save clicked")

    print("\n[5/5] re-reading auth state...")
    time.sleep(2)
    final = get_skills(token)
    final_ids = {s["id"] for s in final}
    print(f"      now {len(final)} skills:")
    for s in final:
        print(f"        rank={s.get('rank')} {s.get('name','?')} (id={s.get('id','?')})")

    diff_in = target_ids_set & final_ids
    diff_out = target_ids_set - final_ids
    print(f"\nresult: {len(diff_in)}/{len(target_ids_set)} target skills present")
    if diff_out:
        print(f"missing: {sorted(diff_out)}")


if __name__ == "__main__":
    main()
