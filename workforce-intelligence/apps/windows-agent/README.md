# Workforce Intelligence — Windows Agent

A small, **visible** .NET 8 desktop agent for **company-owned** Windows
computers, part of the transparent, consent-based Workforce Intelligence
platform. Employees are informed that these devices are monitored.

It reports **activity metadata only** — which application and window is in
focus, for how long, and whether the workstation is idle or locked — so the
platform can understand how work gets done. **This is not spyware.**

---

## What it collects

- **Active window title** (the OS title-bar text of the foreground window).
- **Active application / process name** (e.g. `Code.exe`, `chrome.exe`).
- **Focus intervals** — start/end time and `active_seconds` for each stretch a
  window held focus. A new interval starts when the app, the window title, the
  idle state, or the lock state changes.
- **Idle state** — derived from *time since last input only* (Win32
  `GetLastInputInfo`). After `IdleThresholdSeconds` of no input the interval is
  marked idle and stops accruing active time.
- **Lock / unlock state** — from the OS session-switch notification.
- **Heartbeat** — a periodic liveness ping with current idle seconds and lock
  state.

All of this is **outbound-only** telemetry. The agent buffers it locally (so
nothing is lost during a backend outage) and uploads it in batches.

## What it DELIBERATELY does NOT collect

This agent **never**:

- ❌ captures typed characters / keystrokes (it reads *time since* last input,
  never *what* was typed);
- ❌ reads other processes' memory;
- ❌ takes screenshots or scrapes window contents;
- ❌ records the webcam or microphone;
- ❌ reads clipboard, passwords, secrets, tokens, or MFA codes;
- ❌ captures page or document contents (content capture, where it exists at
  all, is the browser extension's job and is allowlist-gated and off by
  default);
- ❌ executes anything received from the network. **There is no inbound command
  channel.** The backend only ever returns acknowledgements and *non-executable
  config* (intervals, allowlist), which is consumed strictly as data;
- ❌ hides itself, resists removal, evades antivirus, or runs with any stealth
  or persistence-evasion. It is a normal, visible Windows application.

See the repository-level [`SECURITY.md`](../../SECURITY.md) and
[`CLAUDE.md`](../../CLAUDE.md) for the full product boundaries.

## Visibility

The agent is a normal console/worker executable named
**`WorkforceIntelligenceAgent.exe`**. It runs in the foreground (or as an
ordinary service/scheduled task if your deployment wraps it that way) and is
**visible in Task Manager** and, when installed via your MSI/installer, in
**Settings → Apps → Installed apps** (and the old Control Panel "Programs and
Features"). There are no hidden processes.

## Configuration (`appsettings.json`)

The file ships next to the executable. Fill in the backend URL and the device
credential issued during provisioning:

```json
{
  "ApiBaseUrl": "https://workforce.example.com",
  "DeviceKey": "REPLACE_WITH_DEVICE_KEY",
  "DeviceSecret": "REPLACE_WITH_DEVICE_SECRET",
  "PollSeconds": 2,
  "IdleThresholdSeconds": 300,
  "HeartbeatSeconds": 60,
  "BatchMax": 200,
  "SqlitePath": ""
}
```

| Key | Meaning | Default |
| --- | --- | --- |
| `ApiBaseUrl` | Backend base URL. | — (required) |
| `DeviceKey` | Device credential, sent as `X-Device-Key`. | — (required) |
| `DeviceSecret` | Device credential, sent as `X-Device-Secret`. | — (required) |
| `PollSeconds` | Foreground poll cadence. | `2` |
| `IdleThresholdSeconds` | No-input seconds before "idle". | `300` |
| `HeartbeatSeconds` | Heartbeat cadence. | `60` |
| `BatchMax` | Max events per upload batch. | `200` |
| `SqlitePath` | Local buffer file. Empty ⇒ `%LOCALAPPDATA%\WorkforceIntelligenceAgent\buffer.db`. | per-user default |

Any value may also be overridden with a `WIA_`-prefixed environment variable
(e.g. `WIA_ApiBaseUrl`, `WIA_DeviceSecret`) — handy for keeping secrets out of
the config file.

The agent calls `GET /api/v1/agent/config` at startup and may tune its
heartbeat cadence and batch size from the response. That response is **data
only** and is never executed.

## Build & run

Requires the **.NET 8 SDK on Windows** (the project targets `net8.0-windows`
for the Win32 and session APIs).

```powershell
cd apps\windows-agent

# Development run
dotnet run

# Release build
dotnet build -c Release
# -> bin\Release\net8.0-windows\WorkforceIntelligenceAgent.exe
```

Stop the agent with **Ctrl+C**; it closes the open interval, makes a best-effort
final upload, and leaves anything unsent in the local buffer for the next run.

## Backend API (device-authenticated)

Every request sends `X-Device-Key` and `X-Device-Secret` headers. Identity is
derived server-side from the device record, never from a client-supplied id.

- `POST {ApiBaseUrl}/api/v1/agent/events/batch` — `{ "events": [ActivityEvent, ...] }`.
  On HTTP 2xx the uploaded rows are deleted from the local buffer.
- `POST {ApiBaseUrl}/api/v1/agent/heartbeat` — `{ reported_at, agent_version, idle_seconds, is_locked }`.
- `GET  {ApiBaseUrl}/api/v1/agent/config` — non-executable config (intervals,
  allowlist). Data only.

`ActivityEvent = { client_event_id, application, window_title, started_at,
ended_at, active_seconds, is_idle, is_locked }` (timestamps are ISO-8601 UTC;
`client_event_id` is a per-event GUID used for idempotent retries).

## Uninstall / stop collecting

- If started with `dotnet run` or by launching the executable: press **Ctrl+C**
  or close the window.
- If installed with an MSI/installer: remove it from **Settings → Apps →
  Installed apps** (or Control Panel → *Programs and Features*) with the normal
  Windows uninstaller. If it was registered as a Windows Service or Scheduled
  Task, stop/disable that entry as well.
- The local buffer file (`SqlitePath`, default under
  `%LOCALAPPDATA%\WorkforceIntelligenceAgent\`) can be deleted afterward to
  remove any locally buffered, not-yet-uploaded metadata.

There is nothing hidden to clean up: the agent installs no drivers, hooks, or
persistence mechanisms beyond the process itself and its config/buffer files.
