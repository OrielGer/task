# Workforce Intelligence — Browser Extension (Chrome / Edge, MV3)

Company work-analytics browser agent. It reports **active-tab visit metadata**
(sanitized) and captures **business text on allowlisted domains only**, with
**local secret redaction** before anything is sent.

## What it collects
- The **active tab only**: browser, domain, **sanitized** URL (sensitive query
  params stripped), page title, active start/end, active duration, focus state.
  Background tabs are never counted as active work (uses window-focus + idle).
- On **allowlisted business domains only**: debounced snapshots of the text in
  recognized editors (`textarea`, text inputs, `contenteditable`, rich-text
  editors), plus an immediate snapshot on Save/Publish/Send/Submit, stored as
  versioned business content.

## What it deliberately does NOT do
- **No keylogging** — it reads the *current text* of an editor on a debounce,
  never individual keystrokes.
- **Never** reads `input[type="password"]` or any field detected to hold
  credentials, secrets, payment data, MFA/OTP codes, tokens, or keys.
- No capture on non-allowlisted domains (visit metadata only there).
- No remote command execution — it only sends outbound telemetry and fetches
  non-executable config (allowlist + intervals), which it never executes.

Redaction (`src/redaction.ts`) is the TypeScript port of the backend
`SecretRedactor` and runs on the machine **before** upload; the backend redacts
again as defense in depth.

## Build & load
```bash
cd apps/browser-extension
npm install
npm run build          # bundles to dist/
npm test               # runs the redaction unit tests (9 tests)
npm run typecheck      # tsc --noEmit
```
Then in Chrome or Edge:
1. Open `chrome://extensions` (or `edge://extensions`).
2. Enable **Developer mode**.
3. **Load unpacked** → select `apps/browser-extension/dist`.
4. Open the extension's **Options** and set the Backend API URL, the Device key
   and Device secret (from device enrollment), and leave *Collection enabled*
   on. The allowlist is pulled from the backend (`GET /api/v1/agent/config`).

## Device enrollment
An ORG_ADMIN enrolls a device via
`POST /api/v1/organizations/{orgId}/devices/enroll` and pastes the returned
`device_key` / `device_secret` into the extension options. Identity (employee/
org) is derived server-side from the device; the extension cannot assert a
different employee.

## Notes
- `host_permissions: <all_urls>` is required to read active-tab URL/title for
  visit metadata; **content capture is still gated to allowlisted domains** in
  the content script, the background worker, and the server.
- For full editor typing: `npm i -D @types/chrome` is already included.
