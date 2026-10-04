using System.Net.Http.Json;
using System.Text.Json;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Thin HTTP client for the device-authenticated backend endpoints.
///
/// It is OUTBOUND-ONLY: it POSTs telemetry and GETs non-executable config.
/// Nothing returned by the backend is ever executed — the config response is
/// read purely as data to tune cadence.
/// </summary>
public sealed class ApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _baseUrl;
    private readonly JsonSerializerOptions _json;

    public ApiClient(AppConfig config)
    {
        _baseUrl = config.ApiBaseUrl.TrimEnd('/');
        _http = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        // Device credential on every request.
        _http.DefaultRequestHeaders.Add("X-Device-Key", config.DeviceKey);
        _http.DefaultRequestHeaders.Add("X-Device-Secret", config.DeviceSecret);
        _http.DefaultRequestHeaders.Add("User-Agent", $"WorkforceIntelligenceAgent/{Program.AgentVersion}");

        // The source-generated context already bakes in snake_case naming for
        // every registered type; case-insensitive matching keeps deserialization
        // lenient against backend casing changes.
        _json = new JsonSerializerOptions
        {
            TypeInfoResolver = AgentJsonContext.Default,
            PropertyNameCaseInsensitive = true,
        };
    }

    /// <summary>
    /// Upload a batch of events. Returns the server's <see cref="IngestResult"/>
    /// on HTTP 2xx, or null on any non-2xx / transport error (caller keeps the
    /// rows buffered for a later retry).
    /// </summary>
    public async Task<IngestResult?> PostBatchAsync(IReadOnlyList<ActivityEvent> events, CancellationToken ct)
    {
        var body = new ActivityBatch { Events = events };
        using var resp = await _http.PostAsJsonAsync($"{_baseUrl}/api/v1/agent/events/batch", body, _json, ct)
            .ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
        {
            return null;
        }
        return await resp.Content.ReadFromJsonAsync<IngestResult>(_json, ct).ConfigureAwait(false)
            ?? new IngestResult { Accepted = events.Count };
    }

    /// <summary>Send a heartbeat. Returns true on HTTP 2xx.</summary>
    public async Task<bool> HeartbeatAsync(AgentHeartbeat heartbeat, CancellationToken ct)
    {
        using var resp = await _http.PostAsJsonAsync($"{_baseUrl}/api/v1/agent/heartbeat", heartbeat, _json, ct)
            .ConfigureAwait(false);
        return resp.IsSuccessStatusCode;
    }

    /// <summary>
    /// Fetch collector config (DATA ONLY). Returns null on any non-2xx /
    /// transport error so the caller falls back to local defaults.
    /// </summary>
    public async Task<CollectorConfig?> GetConfigAsync(CancellationToken ct)
    {
        using var resp = await _http.GetAsync($"{_baseUrl}/api/v1/agent/config", ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
        {
            return null;
        }
        return await resp.Content.ReadFromJsonAsync<CollectorConfig>(_json, ct).ConfigureAwait(false);
    }

    public void Dispose() => _http.Dispose();
}
