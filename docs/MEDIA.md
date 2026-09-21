# Media provenance and capture gate

Checked 21/09/2026 against base `8a7592d` (OpenAI implementation).

`assets/bridge-demo.gif` originated in `6e1a0f1` (marketing PR #8).
FFprobe reports 800×480, 16.2 seconds, no audio. The original README explicitly
said values were literal tokens rendered into the animation while simultaneously
calling it a screen recording. It is an illustration, not recorded execution.

Source: `extension/service-worker.js` handles `debugger.click` by attaching via
`chrome.debugger`, sending `Input.dispatchMouseEvent` twice, detaching and returning
`{ok: true}`. It does **not** read the resulting DOM event's `isTrusted` value.
`debugger.type` uses CDP `Input.insertText` or `Input.dispatchKeyEvent`.
The old cross-tool comparison therefore had no supporting measurement.

## Real capture still required

The launcher auto-starts/reuses relay port 9224 and its normal Profile-Auto path;
the extension hardcodes the same port. Running it unmodified is not an isolated
demo. No existing browser, profile or relay was accessed for this correction.
A safe future capture should use a disposable OS user/container/display, not just
a fresh tab on the daily profile:

1. Copy this exact repo revision into that disposable environment. Check no relay
   is listening on 9224 there. Launch only that environment's fresh profile.
2. Serve a local synthetic HTML button on an explicitly allowed loopback origin.
   Attach an event listener that stores `{type, isTrusted}` from the **actual
   event** in visible page text. Do not hardcode a successful response.
3. Record the local page and terminal together; run `cb ping`, `cb tabs` and
   `cb debug-click <fixture-tab-id> <button-x> <button-y>` using actual returned IDs.
   Capture the page's event record separately from the bridge acknowledgement.
4. If comparing tools, run each against that same fixture and preserve raw output;
   distinguish DOM `dispatchEvent()` from protocol-level input.
5. Save script, exact source/browser versions, cast/video, checksums, duration and
   per-event assertions. No login, cookies, account requests or music are needed.
6. Stop only the disposable environment's browser and relay.

This is a capture procedure, not evidence that those steps ran. The current slice
changes documentation only; workflows/security edits remain with R1.
