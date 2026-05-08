#!/usr/bin/env python3
"""upwork-portfolio-drive.py — drive Pedro's Upwork Portfolio modal to 6 drafts.

Reuses chrome-bridge primitives. For each item in upwork-portfolio-items.json:
  1. Click Add portfolio button
  2. Fill Project title (textarea)
  3. Fill Your role (textarea)
  4. Fill Project description (textarea)
  5. Add 5 skills via Algolia typeahead (same proven flow as Skills modal)
  6. Click Save as draft (image upload deferred — Pedro adds via modal later)

Pre-req: Profile-Auto Chrome (CfT) running with Pedro logged in.
"""

from __future__ import annotations
import json, sys, time, urllib.request, uuid
from pathlib import Path

RELAY = "http://127.0.0.1:9224"
PROFILE_PAGE = "https://www.upwork.com/freelancers/~01dae7197e964ddf3f"


def cb(kind, args, wait=60):
    jid = uuid.uuid4().hex
    body = json.dumps({"id": jid, "kind": kind, "args": args}).encode()
    urllib.request.urlopen(urllib.request.Request(
        f"{RELAY}/job", data=body, headers={"Content-Type": "application/json"}, method="POST",
    ), timeout=10).read()
    # Long-poll in chunks ≤25s (relay caps wait there)
    deadline = time.time() + wait
    last = None
    while time.time() < deadline:
        try:
            r = urllib.request.urlopen(f"{RELAY}/await/{jid}?wait=20", timeout=25)
            raw = r.read()
            if raw:
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            if e.code != 204:
                return {"ok": False, "error": f"http {e.code}"}
        last = "204-empty"
    return {"ok": False, "error": f"timeout (last={last})"}


def click_at(tab_id, x, y):
    cb("debugger.click", {"tabId": tab_id, "x": x, "y": y})


def find_by_aria(tab_id, aria, scroll=True, timeout_s=10):
    """Poll for an element with given aria-label. Scroll into view + return coords."""
    deadline = time.time() + timeout_s
    code = (
        '(() => {' +
        f'  const el = document.querySelector(\'[aria-label="{aria}"]\');' +
        '  if (!el) return null;' +
        ('  el.scrollIntoView({block:"center", behavior:"instant"});' if scroll else '') +
        '  const r = el.getBoundingClientRect();' +
        '  return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)};' +
        '})()'
    )
    while time.time() < deadline:
        r = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"})
        if r.get("result"):
            return r["result"]
        time.sleep(0.5)
    return None


def fill_textarea(tab_id, aria_label, text):
    """Find textarea by aria-label, focus, type. Polls until visible."""
    code = f"""
(() => {{
  const ta = document.querySelector('textarea[aria-label={json.dumps(aria_label)}], input[aria-label={json.dumps(aria_label)}]');
  if (!ta) return null;
  ta.scrollIntoView({{block:'center', behavior:'instant'}});
  ta.focus();
  ta.select();
  document.execCommand('delete');
  const r = ta.getBoundingClientRect();
  return {{x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)}};
}})()
"""
    deadline = time.time() + 8
    coords = None
    while time.time() < deadline:
        r = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"})
        coords = r.get("result")
        if coords:
            break
        time.sleep(0.5)
    if not coords:
        print(f"  ! textarea {aria_label!r} not found")
        return False
    cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
    time.sleep(0.3)
    cb("debugger.type", {"tabId": tab_id, "text": text})
    return True


def fill_skill(tab_id, skill_name):
    """Type skill into per-portfolio-item Algolia typeahead, click suggestion."""
    code = """
(() => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return null;
  const input = dialog.querySelector('input[placeholder*="add skills" i], input[aria-labelledby*="skills"]');
  if (!input) return null;
  input.scrollIntoView({block:'center', behavior:'instant'});
  input.focus();
  const r = input.getBoundingClientRect();
  return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)};
})()
"""
    inp = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"})["result"]
    if not inp:
        print(f"  ! skills typeahead not found")
        return False
    cb("debugger.click", {"tabId": tab_id, "x": inp["x"], "y": inp["y"]})
    time.sleep(0.4)
    cb("debugger.type", {"tabId": tab_id, "text": skill_name})
    time.sleep(2.0)

    # Click suggestion: exact-text match outside chip area
    sug_code = f"""
(() => {{
  const target = {json.dumps(skill_name)};
  const all = Array.from(document.querySelectorAll('[role="dialog"] *'));
  const matches = all.filter(e => (e.textContent || '').trim().toLowerCase() === target.toLowerCase() && e.children.length === 0);
  const fresh = matches.filter(e => !e.closest('ol.air3-sortable-list, ol[class*="token"]'));
  const pick = fresh[0] || matches[0];
  if (!pick) return null;
  const r = pick.getBoundingClientRect();
  return {{x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)}};
}})()
"""
    coords = cb("scripting.eval", {"tabId": tab_id, "code": sug_code, "world": "MAIN"})["result"]
    if not coords:
        print(f"    ! suggestion {skill_name!r} not found")
        # Clear any typed text via Backspace
        return False
    cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
    time.sleep(0.6)
    return True


def click_save_as_draft(tab_id):
    code = """
(() => {
  const btn = Array.from(document.querySelectorAll('[role="dialog"] button'))
    .find(b => /save as draft/i.test(b.textContent.trim()));
  if (!btn) return null;
  btn.scrollIntoView({block:'center', behavior:'instant'});
  const r = btn.getBoundingClientRect();
  return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2), disabled: btn.disabled};
})()
"""
    coords = cb("scripting.eval", {"tabId": tab_id, "code": code, "world": "MAIN"})["result"]
    if not coords:
        print("  ! Save as draft button not found")
        return False
    if coords.get("disabled"):
        print("  ! Save as draft button disabled")
        return False
    cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
    time.sleep(4)
    return True


def main():
    here = Path(__file__).resolve().parent.parent
    items_file = here / "captures/upwork-portfolio-items.json"
    items = json.loads(items_file.read_text())["items"]

    tab = cb("tabs.query", {"query": {}})["tabs"][0]
    tab_id = tab["id"]

    # Navigate to Pedro's profile
    cb("tabs.update", {"tabId": tab_id, "url": PROFILE_PAGE, "active": True})
    time.sleep(5)

    for i, item in enumerate(items, 1):
        print(f"\n=== item {i}/{len(items)}: {item['title'][:50]!r} ===")

        # Open Add portfolio
        coords = find_by_aria(tab_id, "Add portfolio")
        if not coords:
            print("  ! Add portfolio button not found — Pedro logged in?")
            sys.exit(2)
        cb("debugger.click", {"tabId": tab_id, "x": coords["x"], "y": coords["y"]})
        time.sleep(5)

        # Fill fields
        ok_t = fill_textarea(tab_id, "Project title", item["title"])
        time.sleep(0.6)
        ok_r = fill_textarea(tab_id, "Your role (optional)", item["role"])
        time.sleep(0.6)
        ok_d = fill_textarea(tab_id, "Project description", item["description"])
        time.sleep(0.6)
        print(f"  fields: title={ok_t} role={ok_r} desc={ok_d}")

        # Fill skills (5 each)
        skill_results = []
        for sk in item["skills"]:
            ok = fill_skill(tab_id, sk)
            skill_results.append((sk, ok))
        ok_skills = sum(1 for _, ok in skill_results if ok)
        print(f"  skills: {ok_skills}/{len(item['skills'])}")

        # Save as draft
        ok_save = click_save_as_draft(tab_id)
        print(f"  save: {ok_save}")
        if not ok_save:
            print("  ! aborting — close modal manually + retry")
            sys.exit(3)

        # Wait for modal to close
        time.sleep(2)

    print(f"\n[done] {len(items)} portfolio drafts created")


if __name__ == "__main__":
    main()
