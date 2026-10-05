/**
 * Content script: business-text version capture on ALLOWLISTED domains only.
 *
 * This is NOT a keylogger. It never reads keystrokes; it reads the CURRENT text
 * of a recognized editor on a debounce (or on a Save/Publish/Send/Submit
 * action), redacts it locally, and hands a snapshot to the background worker.
 * Password fields and any credential/secret/payment/MFA fields are NEVER read.
 */
import { redactText } from "./redaction";

type Snapshot = {
  source: string;
  url: string;
  content_type: string;
  external_reference: string | null;
  content: string;
  is_final: boolean;
};

let enabled = false;
let debounceSeconds = 5;
let debounceTimer: number | undefined;
let lastSentHash = "";

function sourceForHost(host: string): string {
  const h = host.toLowerCase();
  if (h.endsWith("docs.google.com")) return "google_docs";
  if (h.endsWith("business.facebook.com") || h.endsWith("facebook.com")) return "meta_ads";
  if (h.endsWith("ads.google.com")) return "google_ads";
  if (h.endsWith("hubspot.com")) return "hubspot";
  if (h.endsWith("linkedin.com")) return "linkedin_ads";
  return "other";
}

/** Fields we must never read. */
function isSensitiveField(el: Element): boolean {
  if (el instanceof HTMLInputElement) {
    const type = (el.type || "").toLowerCase();
    if (type === "password") return true;
    if (["email", "tel", "number"].includes(type) === false) {
      // continue to attribute checks
    }
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    if (/current-password|new-password|one-time-code|cc-number|cc-csc|cc-exp/.test(ac)) return true;
  }
  const hay = [
    el.getAttribute("name"),
    el.getAttribute("id"),
    el.getAttribute("aria-label"),
    el.getAttribute("placeholder"),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return /pass(word|wd)?|otp|mfa|2fa|cvc|cvv|card\s*number|secret|token|ssn|\bpin\b|security\s*code/.test(hay);
}

/** Editors whose business text we may snapshot. */
function isCapturableEditor(el: Element): boolean {
  if (isSensitiveField(el)) return false;
  if (el instanceof HTMLTextAreaElement) return true;
  if (el instanceof HTMLElement && el.isContentEditable) return true;
  if (el instanceof HTMLInputElement) {
    const type = (el.type || "text").toLowerCase();
    // Only free-text-like inputs; never password/credential inputs.
    return ["text", "search", "url"].includes(type);
  }
  return false;
}

function editorText(el: Element): string {
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLInputElement) return el.value || "";
  if (el instanceof HTMLElement) return el.innerText || "";
  return "";
}

function contentTypeFor(el: Element): string {
  if (el instanceof HTMLTextAreaElement) return "long_text";
  if (el instanceof HTMLElement && el.isContentEditable) return "rich_text";
  return "short_text";
}

function cheapHash(s: string): string {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h << 5) - h + s.charCodeAt(i);
    h |= 0;
  }
  return String(h);
}

function snapshot(el: Element, isFinal: boolean): void {
  if (!enabled) return;
  if (!isCapturableEditor(el)) return;
  const raw = editorText(el).trim();
  if (!raw) return;
  const redacted = redactText(raw);
  const h = cheapHash(redacted) + (isFinal ? ":final" : "");
  if (!isFinal && h === lastSentHash) return; // no meaningful change
  lastSentHash = h;

  const payload: Snapshot = {
    source: sourceForHost(location.hostname),
    url: location.href,
    content_type: contentTypeFor(el),
    external_reference: location.pathname.length > 1 ? location.hostname + location.pathname : null,
    content: redacted,
    is_final: isFinal,
  };
  try {
    chrome.runtime.sendMessage({ type: "wfi-content-snapshot", payload });
  } catch {
    /* worker asleep; it will catch subsequent snapshots */
  }
}

function onInput(e: Event): void {
  const t = e.target as Element | null;
  if (!t || !isCapturableEditor(t)) return;
  window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => snapshot(t, false), debounceSeconds * 1000);
}

function looksLikeFinalAction(el: Element): boolean {
  const label = (el.textContent || "").trim().toLowerCase();
  const aria = (el.getAttribute?.("aria-label") || "").toLowerCase();
  const hay = label + " " + aria;
  return /\b(save|publish|send|submit|post|schedule)\b/.test(hay);
}

function onClick(e: Event): void {
  let el = e.target as Element | null;
  for (let i = 0; el && i < 4; i++) {
    if ((el instanceof HTMLButtonElement || el.getAttribute?.("role") === "button" || el instanceof HTMLAnchorElement) && looksLikeFinalAction(el)) {
      captureActiveEditor(true);
      return;
    }
    el = el.parentElement;
  }
}

function onKeydown(e: KeyboardEvent): void {
  // Ctrl/Cmd+S → treat as a save (final) action.
  if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
    captureActiveEditor(true);
  }
}

function onSubmit(): void {
  captureActiveEditor(true);
}

function captureActiveEditor(isFinal: boolean): void {
  const active = document.activeElement;
  if (active && isCapturableEditor(active)) snapshot(active, isFinal);
}

async function init(): Promise<void> {
  const resp = await chrome.runtime.sendMessage({ type: "wfi-get-allowlist" }).catch(() => null);
  if (!resp || !resp.enabled) return;
  const allowlist: string[] = resp.allowlist || [];
  const host = location.hostname.toLowerCase();
  const allowed = allowlist.some((a) => {
    const al = (a || "").toLowerCase().trim();
    return !!al && (host === al || host.endsWith("." + al));
  });
  if (!allowed) return; // Not an approved business domain → capture nothing.
  debounceSeconds = resp.debounce || 5;

  document.addEventListener("input", onInput, true);
  document.addEventListener("click", onClick, true);
  document.addEventListener("keydown", onKeydown, true);
  document.addEventListener("submit", onSubmit, true);
}

void init();
