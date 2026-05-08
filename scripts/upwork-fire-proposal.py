#!/usr/bin/env python3
"""upwork-fire-proposal.py — fire ONE pre-staged proposal end-to-end.

Handles:
  - Activate tab
  - Select duration combobox (default "Less than 1 month")
  - Re-fill milestone description via debugger.type (real keystrokes; Vue rejects native setter)
  - Fill any screening question textarea with the provided answer
  - Click Send → opens 3-things modal
  - Click "agree" checkbox
  - Click Continue to submit
  - Verify proposal-submitted URL + clear has_send

Usage:
  upwork-fire-proposal.py <tab_id> <milestone_desc> [--duration LABEL] [--screening-answer "..."]
  upwork-fire-proposal.py <tab_id> --hourly --rate <N>      # for hourly jobs
"""

from __future__ import annotations
import argparse, json, sys, time, urllib.request, uuid

RELAY = "http://127.0.0.1:9224"


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


def js(tid, code, wait=15):
    return cb("scripting.eval", {"tabId": tid, "code": code, "world": "MAIN"}, wait=wait).get("result")


def click(tid, x, y):
    cb("debugger.click", {"tabId": tid, "x": x, "y": y})


def type_text(tid, text, wait=120):
    cb("debugger.type", {"tabId": tid, "text": text}, wait=wait)


def activate(tid):
    cb("tabs.update", {"tabId": tid, "active": True})
    time.sleep(2.5)


def select_duration(tid, label="Less than 1 month") -> bool:
    """Open duration combobox + click option matching label."""
    coords = js(tid, """
    (() => {
      const c = Array.from(document.querySelectorAll('[role="combobox"]')).find(c => /select a duration|month|week/i.test(c.textContent || ''));
      if (!c) return null;
      c.scrollIntoView({block:'center'});
      const r = c.getBoundingClientRect();
      return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)};
    })()
    """)
    if not coords:
        return False
    click(tid, coords["x"], coords["y"])
    time.sleep(1.0)
    opt_coords = js(tid, f"""
    (() => {{
      const opts = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"], li[class*="dropdown-item"]'));
      const m = opts.find(o => o.textContent.trim() === {json.dumps(label)});
      if (!m) return null;
      const r = m.getBoundingClientRect();
      return {{x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)}};
    }})()
    """)
    if not opt_coords:
        return False
    click(tid, opt_coords["x"], opt_coords["y"])
    time.sleep(0.5)
    return True


def refill_milestone(tid, desc):
    """Re-fill milestone description via real keystrokes (Vue rejects native setter)."""
    coords = js(tid, """
    (() => {
      const desc = document.querySelector('input[aria-label="Description 1"]');
      if (!desc) return null;
      desc.scrollIntoView({block:'center'});
      desc.focus();
      desc.select();
      document.execCommand('delete');
      const r = desc.getBoundingClientRect();
      return {x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)};
    })()
    """)
    if not coords:
        return False
    click(tid, coords["x"], coords["y"])
    time.sleep(0.4)
    type_text(tid, desc)
    time.sleep(0.3)
    return True


def fill_screening_question(tid, question_substr, answer):
    """Find textarea inside form-group whose text matches substr, fill answer."""
    coords = js(tid, f"""
    (() => {{
      const groups = Array.from(document.querySelectorAll('[class*="form-group"]')).filter(g => g.textContent.toLowerCase().includes({json.dumps(question_substr.lower())}));
      if (!groups.length) return null;
      const ta = groups[0].querySelector('textarea, input[type="text"]');
      if (!ta) return null;
      ta.scrollIntoView({{block:'center'}});
      ta.focus();
      ta.select();
      document.execCommand('delete');
      return new Promise(r => setTimeout(() => {{
        const re = ta.getBoundingClientRect();
        r({{x: Math.round(re.x+re.width/2), y: Math.round(re.y+re.height/2)}});
      }}, 600));
    }})()
    """)
    if not coords:
        return False
    click(tid, coords["x"], coords["y"])
    time.sleep(0.4)
    type_text(tid, answer)
    return True


def click_send(tid) -> dict | None:
    coords = js(tid, """
    (() => {
      const send = Array.from(document.querySelectorAll('button')).find(b => /^\\s*Send for /i.test(b.textContent || ''));
      if (!send) return null;
      send.scrollIntoView({block:'center', behavior:'instant'});
      return new Promise(r => setTimeout(() => {
        const re = send.getBoundingClientRect();
        r({x: Math.round(re.x+re.width/2), y: Math.round(re.y+re.height/2), label: send.textContent.trim()});
      }, 800));
    })()
    """)
    if not coords:
        return None
    click(tid, coords["x"], coords["y"])
    time.sleep(3.0)
    return coords


def click_agree_and_continue(tid) -> bool:
    """In 3-things modal: click agree checkbox + Continue button.

    Modal can scroll the checkbox off-screen. Always scrollIntoView FIRST."""
    cb_coords = js(tid, """
    (() => {
      const cb = document.querySelector('input[type="checkbox"][value="agree"]');
      if (!cb) return null;
      let wrapper = cb.parentElement;
      for (let i = 0; i < 5 && wrapper; i++) {
        if ((wrapper.className || '').includes('checkbox-label') || wrapper.tagName === 'LABEL') break;
        wrapper = wrapper.parentElement;
      }
      if (wrapper) wrapper.scrollIntoView({block:'center'});
      return new Promise(r => setTimeout(() => {
        const fake = wrapper && wrapper.querySelector('.air3-checkbox-fake-input');
        const target = fake || wrapper;
        if (!target) return r(null);
        const re = target.getBoundingClientRect();
        r({x: Math.round(re.x+re.width/2), y: Math.round(re.y+re.height/2), checked: cb.checked, visible: re.width > 0 && re.y > 0});
      }, 600));
    })()
    """)
    if cb_coords and cb_coords.get("visible"):
        if not cb_coords.get("checked"):
            click(tid, cb_coords["x"], cb_coords["y"])
            time.sleep(0.7)
    cont = js(tid, """
    (() => {
      const c = Array.from(document.querySelectorAll('button')).find(b => /Continue\\s*\\b.*submit/i.test(b.textContent || ''));
      if (!c) return null;
      c.scrollIntoView({block:'center'});
      return new Promise(r => setTimeout(() => {
        const re = c.getBoundingClientRect();
        r({x: Math.round(re.x+re.width/2), y: Math.round(re.y+re.height/2), disabled: c.disabled});
      }, 600));
    })()
    """)
    if not cont or cont.get("disabled"):
        return False
    click(tid, cont["x"], cont["y"])
    time.sleep(7)
    return True


def verify_sent(tid):
    return js(tid, """
    (() => ({
      url: location.href,
      title: document.title,
      has_send: !!Array.from(document.querySelectorAll('button')).find(b => /^\\s*Send for /i.test(b.textContent || '')),
      has_3things: document.body.innerText.includes('3 things you need to know'),
      proposal_id: (location.href.match(/proposals\\/([0-9]+)/) || [])[1] || null,
      success_url: location.href.includes('?success'),
    }))()
    """)


def fire_fixed(tid, milestone_desc, screening_question=None, screening_answer=None, duration="Less than 1 month"):
    """Fire one fixed-price proposal end-to-end."""
    print(f"\n=== firing fixed-price tab {tid} ===")
    activate(tid)

    print("  selecting duration...")
    ok = select_duration(tid, duration)
    print(f"    duration: {ok}")

    print("  re-filling milestone description...")
    ok = refill_milestone(tid, milestone_desc)
    print(f"    milestone: {ok}")

    if screening_question and screening_answer:
        print(f"  filling screening question: {screening_question[:40]!r}")
        ok = fill_screening_question(tid, screening_question, screening_answer)
        print(f"    screening: {ok}")

    print("  clicking Send...")
    sc = click_send(tid)
    print(f"    send: {sc}")
    if not sc:
        print("    ! aborting — Send btn not found")
        return False

    print("  agree + Continue...")
    ok = click_agree_and_continue(tid)
    print(f"    continue: {ok}")

    state = verify_sent(tid)
    print(f"  state: {state}")
    return bool(state.get("success_url"))


if __name__ == "__main__":
    print("Library module — import + call fire_fixed(tid, ...) per pick.")
