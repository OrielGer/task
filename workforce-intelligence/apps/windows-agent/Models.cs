using System.Globalization;
using System.Text.Json.Serialization;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Local configuration, loaded from appsettings.json (and optional WIA_*
/// environment variables). All values are plain data — nothing here is ever
/// executed.
/// </summary>
public sealed class AppConfig
{
    /// <summary>Backend base URL, e.g. "https://workforce.example.com".</summary>
    public string ApiBaseUrl { get; set; } = "";

    /// <summary>Device credential (sent as the X-Device-Key header).</summary>
    public string DeviceKey { get; set; } = "";

    /// <summary>Device credential (sent as the X-Device-Secret header).</summary>
    public string DeviceSecret { get; set; } = "";

    /// <summary>Foreground poll cadence in seconds.</summary>
    public int PollSeconds { get; set; } = 2;

    /// <summary>Seconds of no input before the user is considered idle.</summary>
    public int IdleThresholdSeconds { get; set; } = 300;

    /// <summary>Heartbeat cadence in seconds.</summary>
    public int HeartbeatSeconds { get; set; } = 60;

    /// <summary>Maximum events uploaded per batch.</summary>
    public int BatchMax { get; set; } = 200;

    /// <summary>Path to the local SQLite buffer file. Empty => a per-user default.</summary>
    public string SqlitePath { get; set; } = "";

    /// <summary>Fill in defaults and clamp values to safe minimums.</summary>
    public void ApplyDefaults()
    {
        if (PollSeconds < 1) PollSeconds = 2;
        if (IdleThresholdSeconds < 1) IdleThresholdSeconds = 300;
        if (HeartbeatSeconds < 5) HeartbeatSeconds = 60;
        if (BatchMax < 1) BatchMax = 200;

        if (string.IsNullOrWhiteSpace(SqlitePath))
        {
            var dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "WorkforceIntelligenceAgent");
            SqlitePath = Path.Combine(dir, "buffer.db");
        }
    }
}

/// <summary>
/// One completed focus interval. This is the ONLY telemetry shape the agent
/// sends. It carries metadata about which app/window was focused and for how
/// long — never keystrokes, screen contents, or process memory.
/// </summary>
public sealed class ActivityEvent
{
    /// <summary>Client-generated idempotency key (&lt;= 64 chars), unique per event.</summary>
    public string ClientEventId { get; set; } = "";

    /// <summary>Process/app name, e.g. "Code.exe" or "chrome.exe".</summary>
    public string Application { get; set; } = "";

    /// <summary>Active window title as shown in the OS title bar.</summary>
    public string WindowTitle { get; set; } = "";

    /// <summary>Interval start (ISO-8601 UTC).</summary>
    public string StartedAt { get; set; } = "";

    /// <summary>Interval end (ISO-8601 UTC).</summary>
    public string EndedAt { get; set; } = "";

    /// <summary>Seconds in this interval spent NOT idle and NOT locked.</summary>
    public int ActiveSeconds { get; set; }

    /// <summary>True when the interval represents an idle (no-input) stretch.</summary>
    public bool IsIdle { get; set; }

    /// <summary>True when the workstation was locked for this interval.</summary>
    public bool IsLocked { get; set; }
}

/// <summary>Request body for POST /api/v1/agent/events/batch.</summary>
public sealed class ActivityBatch
{
    public IReadOnlyList<ActivityEvent> Events { get; set; } = Array.Empty<ActivityEvent>();
}

/// <summary>Request body for POST /api/v1/agent/heartbeat.</summary>
public sealed class AgentHeartbeat
{
    public string ReportedAt { get; set; } = "";
    public string AgentVersion { get; set; } = "";

    /// <summary>Seconds since last user input (time only — NOT what was typed).</summary>
    public int IdleSeconds { get; set; }
    public bool IsLocked { get; set; }
}

/// <summary>Response body from the batch/heartbeat ingest endpoints.</summary>
public sealed class IngestResult
{
    public int Accepted { get; set; }
    public int Duplicates { get; set; }
    public int Rejected { get; set; }
}

/// <summary>
/// Non-executable config returned by GET /api/v1/agent/config. This is DATA
/// ONLY — the agent uses the numeric fields to tune its own cadence and never
/// treats any field as code or a command.
/// </summary>
public sealed class CollectorConfig
{
    /// <summary>
    /// Business domains where the browser extension may capture page text.
    /// Not used by this agent (it captures no page content); kept for parity
    /// with the shared wire contract.
    /// </summary>
    public List<string> AllowlistedDomains { get; set; } = new();
    public int ContentDebounceSeconds { get; set; }
    public int HeartbeatSeconds { get; set; }
    public int BatchMax { get; set; }
}

/// <summary>Timestamp formatting helpers.</summary>
public static class TimeUtil
{
    /// <summary>Format an instant as ISO-8601 in UTC with a trailing 'Z'.</summary>
    public static string IsoUtc(DateTimeOffset t) =>
        t.UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ss.fffffffZ", CultureInfo.InvariantCulture);
}

/// <summary>
/// Source-generated JSON context (keeps serialization trim/AOT-friendly and
/// avoids reflection warnings). snake_case matches the backend contract.
/// </summary>
[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower)]
[JsonSerializable(typeof(ActivityBatch))]
[JsonSerializable(typeof(ActivityEvent))]
[JsonSerializable(typeof(AgentHeartbeat))]
[JsonSerializable(typeof(IngestResult))]
[JsonSerializable(typeof(CollectorConfig))]
public partial class AgentJsonContext : JsonSerializerContext
{
}
