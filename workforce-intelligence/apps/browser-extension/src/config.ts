/** Extension configuration, persisted in chrome.storage.local. */

export interface ExtConfig {
  apiBaseUrl: string;
  deviceKey: string;
  deviceSecret: string;
  allowlistedDomains: string[];
  contentDebounceSeconds: number;
  heartbeatSeconds: number;
  batchMax: number;
  /** Master switch; when false the extension collects nothing. */
  enabled: boolean;
}

export const DEFAULT_CONFIG: ExtConfig = {
  apiBaseUrl: "http://localhost:8000",
  deviceKey: "",
  deviceSecret: "",
  allowlistedDomains: [],
  contentDebounceSeconds: 5,
  heartbeatSeconds: 60,
  batchMax: 200,
  enabled: true,
};

export async function getConfig(): Promise<ExtConfig> {
  const stored = await chrome.storage.local.get(DEFAULT_CONFIG as unknown as Record<string, unknown>);
  return { ...DEFAULT_CONFIG, ...stored } as ExtConfig;
}

export async function setConfig(patch: Partial<ExtConfig>): Promise<void> {
  await chrome.storage.local.set(patch);
}

/** Exact or subdomain match against the configured allowlist. */
export function isDomainAllowed(domain: string, allowlist: string[]): boolean {
  const d = domain.toLowerCase().trim();
  if (!d) return false;
  return allowlist.some((a) => {
    const al = a.toLowerCase().trim();
    return !!al && (d === al || d.endsWith("." + al));
  });
}
