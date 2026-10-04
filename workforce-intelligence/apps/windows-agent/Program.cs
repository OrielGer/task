using Microsoft.Extensions.Configuration;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Entry point and main loop for the Workforce Intelligence Windows Agent.
///
/// The loop does four things on a cadence:
///   1. Poll the foreground window and build focus intervals (ActiveWindowTracker).
///   2. Buffer completed intervals locally (EventBuffer / SQLite).
///   3. Flush buffered events to the backend in batches (ApiClient).
///   4. Send a heartbeat on an interval.
///
/// It is outbound-only. There is no inbound command channel: the backend's only
/// responses are acknowledgements and non-executable config.
/// </summary>
public static class Program
{
    public const string AgentVersion = "1.0.0";

    // How often to attempt a flush even when the buffer isn't full.
    private const int FlushIntervalSeconds = 15;

    public static async Task<int> Main()
    {
        Console.WriteLine($"Workforce Intelligence Agent v{AgentVersion}");
        Console.WriteLine("Collects activity METADATA only (active app/window, durations, idle/lock, heartbeat).");
        Console.WriteLine("No keystrokes, no screenshots, no remote commands. Press Ctrl+C to stop.");

        // Windows-only: all collection APIs (Win32 P/Invoke + SystemEvents)
        // require Windows. Fail clearly elsewhere instead of crashing.
        if (!OperatingSystem.IsWindows())
        {
            Console.Error.WriteLine("ERROR: This agent uses Windows-only APIs and must run on Windows.");
            return 1;
        }

        AppConfig cfg;
        try
        {
            cfg = LoadConfig();
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"ERROR: failed to load configuration: {ex.Message}");
            return 1;
        }

        if (string.IsNullOrWhiteSpace(cfg.ApiBaseUrl) ||
            string.IsNullOrWhiteSpace(cfg.DeviceKey) ||
            string.IsNullOrWhiteSpace(cfg.DeviceSecret) ||
            cfg.DeviceKey.StartsWith("REPLACE_", StringComparison.OrdinalIgnoreCase))
        {
            Console.Error.WriteLine("ERROR: ApiBaseUrl, DeviceKey and DeviceSecret must be set in appsettings.json.");
            return 1;
        }

        return await RunAsync(cfg).ConfigureAwait(false);
    }

    private static AppConfig LoadConfig()
    {
        IConfigurationRoot configuration = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json", optional: false, reloadOnChange: false)
            // Optional overrides, e.g. WIA_ApiBaseUrl / WIA_DeviceSecret.
            .AddEnvironmentVariables(prefix: "WIA_")
            .Build();

        var cfg = configuration.Get<AppConfig>() ?? new AppConfig();
        cfg.ApplyDefaults();
        return cfg;
    }

    private static async Task<int> RunAsync(AppConfig cfg)
    {
        using var cts = new CancellationTokenSource();
        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true; // handle shutdown ourselves instead of hard-killing
            Console.WriteLine("Shutdown requested; flushing buffer...");
            cts.Cancel();
        };

        var idle = new IdleMonitor();
        using var session = new SessionStateMonitor();
        using var buffer = new EventBuffer(cfg.SqlitePath);
        using var api = new ApiClient(cfg);
        var tracker = new ActiveWindowTracker(cfg, idle, session);

        Console.WriteLine($"Buffering to: {cfg.SqlitePath}");
        Console.WriteLine($"Backend: {cfg.ApiBaseUrl}");

        // Effective cadence, optionally tuned by backend config (data only).
        int heartbeatSeconds = cfg.HeartbeatSeconds;
        int batchMax = cfg.BatchMax;
        try
        {
            var remote = await api.GetConfigAsync(cts.Token).ConfigureAwait(false);
            if (remote != null)
            {
                if (remote.HeartbeatSeconds > 0) heartbeatSeconds = remote.HeartbeatSeconds;
                if (remote.BatchMax > 0) batchMax = remote.BatchMax;
                // remote.AllowlistedDomains / ContentDebounceSeconds target the
                // browser content collector; this agent captures no page content.
                Console.WriteLine($"Applied backend config: heartbeat={heartbeatSeconds}s, batch_max={batchMax}.");
            }
        }
        catch
        {
            Console.WriteLine("Backend config unavailable; using local defaults.");
        }

        var lastHeartbeat = DateTimeOffset.MinValue;
        var lastFlush = DateTimeOffset.UtcNow;

        try
        {
            while (!cts.IsCancellationRequested)
            {
                try
                {
                    var completed = tracker.Poll();
                    if (completed != null)
                    {
                        buffer.Enqueue(completed);
                    }

                    var now = DateTimeOffset.UtcNow;

                    if ((now - lastFlush).TotalSeconds >= FlushIntervalSeconds || buffer.Count() >= batchMax)
                    {
                        await FlushAsync(buffer, api, batchMax, cts.Token).ConfigureAwait(false);
                        lastFlush = now;
                    }

                    if ((now - lastHeartbeat).TotalSeconds >= heartbeatSeconds)
                    {
                        await SendHeartbeatAsync(api, idle, session, cts.Token).ConfigureAwait(false);
                        lastHeartbeat = now;
                    }
                }
                catch (OperationCanceledException)
                {
                    break;
                }
                catch (Exception ex)
                {
                    // One bad poll/flush must not kill the agent.
                    Console.Error.WriteLine($"WARN: loop iteration error: {ex.Message}");
                }

                try
                {
                    await Task.Delay(TimeSpan.FromSeconds(cfg.PollSeconds), cts.Token).ConfigureAwait(false);
                }
                catch (OperationCanceledException)
                {
                    break;
                }
            }
        }
        finally
        {
            // Graceful shutdown: close the open interval and make a best-effort
            // final flush. Anything unsent stays buffered for the next run.
            try
            {
                var tail = tracker.FlushCurrent();
                if (tail != null)
                {
                    buffer.Enqueue(tail);
                }
                await FlushAsync(buffer, api, batchMax, CancellationToken.None).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"WARN: shutdown flush failed (data remains buffered): {ex.Message}");
            }
        }

        Console.WriteLine("Agent stopped.");
        return 0;
    }

    /// <summary>Upload buffered events in batches; delete only on HTTP 2xx.</summary>
    private static async Task FlushAsync(EventBuffer buffer, ApiClient api, int batchMax, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            var batch = buffer.DequeueBatch(batchMax);
            if (batch.Count == 0)
            {
                break;
            }

            IngestResult? result;
            try
            {
                var events = batch.Select(b => b.Event).ToList();
                result = await api.PostBatchAsync(events, ct).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                // Transport failure: keep everything buffered, retry later.
                Console.Error.WriteLine($"WARN: batch upload failed, will retry: {ex.Message}");
                break;
            }

            if (result == null)
            {
                // Non-2xx: leave rows buffered for a later attempt.
                break;
            }

            buffer.DeleteAcked(batch.Select(b => b.Id));
            Console.WriteLine(
                $"Flushed {batch.Count} event(s): accepted={result.Accepted}, " +
                $"duplicates={result.Duplicates}, rejected={result.Rejected}.");

            if (batch.Count < batchMax)
            {
                break; // buffer drained
            }
        }
    }

    private static async Task SendHeartbeatAsync(
        ApiClient api, IdleMonitor idle, SessionStateMonitor session, CancellationToken ct)
    {
        var hb = new AgentHeartbeat
        {
            ReportedAt = TimeUtil.IsoUtc(DateTimeOffset.UtcNow),
            AgentVersion = AgentVersion,
            IdleSeconds = idle.GetIdleSeconds(),
            IsLocked = session.IsLocked,
        };

        try
        {
            await api.HeartbeatAsync(hb, ct).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            // Backend unreachable; the next heartbeat will try again.
            Console.Error.WriteLine($"WARN: heartbeat failed: {ex.Message}");
        }
    }
}
