/**
 * Background service worker: tracks the ACTIVE tab only and reports sanitized
 * visit metadata; relays allowlisted-domain content snapshots to the backend.
 *
 * Active work accounting: an "interval" is open only while the browser window
 * is focused, the user is not idle, and a real http(s) tab is active. Any of
 * those changing closes the interval and emits one browser event whose
 * active_seconds is its focused wall-clock duration. Background tabs are never
 * counted. There is no inbound command channel.
 */
import {
  BrowserEventPayload,
  ContentSnapshotPayload,
  fetchCollectorConfig,
  sendBrowserEvents,
  sendContentSnapshots,
  sendHeartbeat,
} from "./api";
import { ExtConfig, getConfig, isDomainAllowed, setConfig } from "./config";
import { redactText, sanitizeUrl } from "./redaction";

const ALARM = "wfi-tick";

interface OpenInterval {
  tabId: number;
  url: string;
  domain: string;
  title: string;
  startedAtMs: number;
}

let idleState: "active" | "idle" | "locked" = "active";
let windowFocused = true;

function uuid(): string {
  // Not security-sensitive; just an idempotency key.
  return (crypto as any).randomUUID ? crypto.randomUUID().replace(/-/g, "") : String(Date.now()) + Math.floor(Math.random() * 1e6);
}

async function getOpen(): Promise<OpenInterval | null> {
  const { __open } = await chrome.storage.local.get("__open");
  return (__open as OpenInterval) || null;
}
async function setOpen(v: OpenInterval | null): Promise<void> {
  await chrome.storage.local.set({ __open: v });
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function isHttp(url: string): boolean {
  return /^https?:\/\//i.test(url);
}

async function enqueue(key: "__q_browser" | "__q_content", item: unknown): Promise<void> {
  const data = await chrome.storage.local.get(key);
  const arr = (data[key] as unknown[]) || [];
  arr.push(item);
  await chrome.storage.local.set({ [key]: arr });
}

/** Close the current interval (if any) and enqueue a browser event. */
async function closeInterval(): Promise<void> {
  const open = await getOpen();
  if (!open) return;
  await setOpen(null);
  const seconds = Math.round((Date.now() - open.startedAtMs) / 1000);
  if (seconds <= 0) return;
  const ev: BrowserEventPayload = {
    client_event_id: uuid(),
    browser: navigator.userAgent.includes("Edg") ? "edge" : "chrome",
    domain: open.domain,
    url: sanitizeUrl(open.url),
    page_title: redactText(open.title),
    started_at: new Date(open.startedAtMs).toISOString(),
    ended_at: new Date().toISOString(),
    active_seconds: seconds,
    focused: true,
  };
  await enqueue("__q_browser", ev);
}

/** Open a new interval for the currently active tab, if conditions allow. */
async function openIntervalForActiveTab(): Promise<void> {
  const cfg = await getConfig();
  if (!cfg.enabled) return;
  if (!windowFocused || idleState !== "active") return;
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !tab.id || !tab.url || !isHttp(tab.url)) return;
  await setOpen({
    tabId: tab.id,
    url: tab.url,
    domain: domainOf(tab.url),
    title: tab.title || "",
    startedAtMs: Date.now(),
  });
}

async function rotate(): Promise<void> {
  await closeInterval();
  await openIntervalForActiveTab();
}

// ── Event wiring ───────────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(async () => {
  chrome.idle.setDetectionInterval(60);
  chrome.alarms.create(ALARM, { periodInMinutes: 1 });
  await refreshRemoteConfig();
});

chrome.runtime.onStartup.addListener(async () => {
  chrome.idle.setDetectionInterval(60);
  chrome.alarms.create(ALARM, { periodInMinutes: 1 });
  await refreshRemoteConfig();
});

chrome.tabs.onActivated.addListener(() => void rotate());
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.title) {
    if (tab.active) void rotate();
  }
});
chrome.windows.onFocusChanged.addListener((windowId) => {
  windowFocused = windowId !== chrome.windows.WINDOW_ID_NONE;
  if (!windowFocused) void closeInterval();
  else void openIntervalForActiveTab();
});
chrome.idle.onStateChanged.addListener((state) => {
  idleState = state as typeof idleState;
  if (idleState !== "active") void closeInterval();
  else void openIntervalForActiveTab();
});

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== ALARM) return;
  await flush();
  const cfg = await getConfig();
  if (cfg.enabled) {
    const seconds = idleState === "active" ? 0 : 300;
    try {
      await sendHeartbeat(cfg, seconds);
    } catch {
      /* offline; will retry next tick */
    }
  }
});

// Content scripts send redacted snapshots here; background uploads them.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "wfi-content-snapshot") {
    void handleContentSnapshot(msg.payload).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
  if (msg && msg.type === "wfi-get-allowlist") {
    void getConfig().then((c) => sendResponse({ allowlist: c.allowlistedDomains, enabled: c.enabled, debounce: c.contentDebounceSeconds }));
    return true;
  }
  return false;
});

async function handleContentSnapshot(p: any): Promise<void> {
  const cfg = await getConfig();
  if (!cfg.enabled) return;
  const domain = domainOf(p.url || "");
  // Enforce allowlist server-side too, but refuse here as the first gate.
  if (!isDomainAllowed(domain, cfg.allowlistedDomains)) return;
  const snapshot: ContentSnapshotPayload = {
    client_event_id: uuid(),
    source: p.source || "other",
    domain,
    url: sanitizeUrl(p.url || ""),
    content_type: p.content_type || "",
    external_reference: p.external_reference ?? null,
    // Defense in depth: re-redact even though the content script already did.
    content: redactText(p.content || ""),
    is_final: !!p.is_final,
    captured_at: new Date().toISOString(),
  };
  await enqueue("__q_content", snapshot);
  await flush();
}

async function flush(): Promise<void> {
  const cfg = await getConfig();
  if (!cfg.enabled || !cfg.deviceKey || !cfg.deviceSecret) return;
  // Ensure an in-progress interval is accounted periodically.
  await rotate();

  const data = await chrome.storage.local.get(["__q_browser", "__q_content"]);
  const browserQ = (data.__q_browser as BrowserEventPayload[]) || [];
  const contentQ = (data.__q_content as ContentSnapshotPayload[]) || [];
  try {
    if (browserQ.length) {
      await sendBrowserEvents(cfg, browserQ.slice(0, cfg.batchMax));
      await chrome.storage.local.set({ __q_browser: browserQ.slice(cfg.batchMax) });
    }
    if (contentQ.length) {
      await sendContentSnapshots(cfg, contentQ.slice(0, cfg.batchMax));
      await chrome.storage.local.set({ __q_content: contentQ.slice(cfg.batchMax) });
    }
  } catch {
    /* backend unreachable; keep queue for next tick */
  }
}

async function refreshRemoteConfig(): Promise<void> {
  const cfg = await getConfig();
  if (!cfg.deviceKey || !cfg.deviceSecret) return;
  const remote = await fetchCollectorConfig(cfg);
  if (remote) {
    const patch: Partial<ExtConfig> = {
      allowlistedDomains: remote.allowlisted_domains,
      contentDebounceSeconds: remote.content_debounce_seconds,
      heartbeatSeconds: remote.heartbeat_seconds,
      batchMax: remote.batch_max,
    };
    await setConfig(patch);
  }
}
