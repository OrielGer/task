/** Options page logic: edit config, show the backend-provided allowlist. */
import { getConfig, setConfig } from "./config";
import { fetchCollectorConfig } from "./api";

async function load(): Promise<void> {
  const cfg = await getConfig();
  (document.getElementById("apiBaseUrl") as HTMLInputElement).value = cfg.apiBaseUrl;
  (document.getElementById("deviceKey") as HTMLInputElement).value = cfg.deviceKey;
  (document.getElementById("deviceSecret") as HTMLInputElement).value = cfg.deviceSecret;
  (document.getElementById("enabled") as HTMLInputElement).checked = cfg.enabled;
  renderAllowlist(cfg.allowlistedDomains);
}

function renderAllowlist(domains: string[]): void {
  const el = document.getElementById("allowlist")!;
  el.textContent = domains.length ? domains.join("\n") : "(none configured yet)";
}

async function save(): Promise<void> {
  const apiBaseUrl = (document.getElementById("apiBaseUrl") as HTMLInputElement).value.trim();
  const deviceKey = (document.getElementById("deviceKey") as HTMLInputElement).value.trim();
  const deviceSecret = (document.getElementById("deviceSecret") as HTMLInputElement).value.trim();
  const enabled = (document.getElementById("enabled") as HTMLInputElement).checked;
  await setConfig({ apiBaseUrl, deviceKey, deviceSecret, enabled });

  // Pull the current allowlist/intervals from the backend (data only).
  const cfg = await getConfig();
  const remote = await fetchCollectorConfig(cfg);
  if (remote) {
    await setConfig({
      allowlistedDomains: remote.allowlisted_domains,
      contentDebounceSeconds: remote.content_debounce_seconds,
      heartbeatSeconds: remote.heartbeat_seconds,
      batchMax: remote.batch_max,
    });
    renderAllowlist(remote.allowlisted_domains);
  }
  const status = document.getElementById("status")!;
  status.textContent = "Saved.";
  setTimeout(() => (status.textContent = ""), 2000);
}

document.getElementById("save")!.addEventListener("click", () => void save());
void load();
