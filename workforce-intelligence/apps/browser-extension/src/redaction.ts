/**
 * Local secret redaction + URL sanitization for the browser extension.
 *
 * This is the TypeScript port of the backend `SecretRedactor`
 * (apps/api/app/redaction.py) and MUST stay behaviorally aligned with it.
 * It runs on the workstation BEFORE any content leaves the machine (see
 * SECURITY.md). When in doubt, redact.
 */

export const REDACTED = "[REDACTED]";

const SENSITIVE_QUERY_PARAMS = new Set<string>([
  "token",
  "access_token",
  "refresh_token",
  "id_token",
  "secret",
  "client_secret",
  "password",
  "passwd",
  "pwd",
  "auth",
  "authorization",
  "code",
  "api_key",
  "apikey",
  "key",
  "sig",
  "signature",
  "session",
  "sessionid",
  "otp",
  "mfa",
]);

// Substrings that make ANY param name sensitive. "key" is intentionally absent
// so innocent params like "keyword" are not eaten.
const SENSITIVE_SUBSTRINGS = ["token", "secret", "password", "passwd", "api_key", "apikey", "auth"];

function isSensitiveParam(name: string): boolean {
  const n = name.toLowerCase();
  if (SENSITIVE_QUERY_PARAMS.has(n)) return true;
  return SENSITIVE_SUBSTRINGS.some((s) => n.includes(s));
}

/** Strip sensitive query-param values and any embedded credentials from a URL. */
export function sanitizeUrl(url: string): string {
  if (!url) return url;
  let u: URL;
  try {
    u = new URL(url);
  } catch {
    // Not an absolute URL we can parse → do not risk leaking; redact wholesale.
    return REDACTED;
  }
  // Remove userinfo (user:pass@host).
  u.username = "";
  u.password = "";
  const params = u.searchParams;
  for (const key of Array.from(params.keys())) {
    if (isSensitiveParam(key)) {
      // Replace every value for this key.
      const values = params.getAll(key);
      params.delete(key);
      for (let i = 0; i < values.length; i++) params.append(key, REDACTED);
    }
  }
  return u.toString();
}

function luhnOk(digits: string): boolean {
  const d = digits.replace(/\D/g, "").split("").map(Number);
  if (d.length < 13) return false;
  let total = 0;
  const parity = d.length % 2;
  for (let i = 0; i < d.length; i++) {
    let n = d[i];
    if (i % 2 === parity) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    total += n;
  }
  return total % 10 === 0;
}

function redactCreditCards(text: string): string {
  return text.replace(/\b(?:\d[ -]?){13,19}\b/g, (m) => (luhnOk(m) ? REDACTED : m));
}

interface Rule {
  name: string;
  pattern: RegExp;
  replacement: string | ((substring: string, ...args: any[]) => string);
}

function defaultRules(): Rule[] {
  return [
    {
      name: "private_key",
      pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
      replacement: REDACTED,
    },
    {
      name: "authorization_header",
      pattern: /(Authorization\s*:\s*)([^\r\n]+)/gi,
      replacement: "$1" + REDACTED,
    },
    {
      name: "bearer_token",
      pattern: /\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi,
      replacement: "Bearer " + REDACTED,
    },
    {
      name: "jwt",
      pattern: /\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b/g,
      replacement: REDACTED,
    },
    {
      name: "secret_kv",
      pattern:
        /\b(pass(?:word|wd)?|secret|client_secret|api[_-]?key|access[_-]?token|refresh[_-]?token|auth[_-]?token|token|otp|mfa|one[_-]?time[_-]?code|verification[_-]?code|private[_-]?key)(\s*["']?\s*[:=]\s*["']?\s*)([^\s"',;]{3,})/gi,
      replacement: "$1$2" + REDACTED,
    },
    {
      name: "provider_api_keys",
      pattern:
        /\b(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|ghp_[0-9A-Za-z]{20,}|xox[baprs]-[0-9A-Za-z-]{10,})\b/g,
      replacement: REDACTED,
    },
  ];
}

export class SecretRedactor {
  private rules: Rule[];

  constructor(extraRules: Rule[] = []) {
    this.rules = [...defaultRules(), ...extraRules];
  }

  redact(text: string | null | undefined): string {
    if (!text) return text || "";
    let out = text;
    for (const rule of this.rules) {
      out = out.replace(rule.pattern, rule.replacement as any);
    }
    out = redactCreditCards(out);
    return out;
  }
}

const defaultRedactor = new SecretRedactor();

export function redactText(text: string | null | undefined): string {
  return defaultRedactor.redact(text);
}
