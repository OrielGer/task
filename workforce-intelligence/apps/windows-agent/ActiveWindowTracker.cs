using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Runtime.Versioning;
using System.Text;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Polls the foreground window and builds FOCUS INTERVALS.
///
/// What it reads (metadata only):
///   - the active window title (GetWindowText)
///   - the owning process/app name (GetWindowThreadProcessId + ProcessName)
///   - idle state (via <see cref="IdleMonitor"/> — time since last input only)
///   - locked state (via <see cref="SessionStateMonitor"/>)
///
/// What it deliberately does NOT do: read keystrokes, read another process's
/// memory, take screenshots, or inspect page/document contents.
///
/// A new interval starts whenever the app, the window title, the idle flag, or
/// the lock flag changes. <see cref="ActivityEvent.ActiveSeconds"/> accumulates
/// only while NOT idle and NOT locked.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class ActiveWindowTracker
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    private readonly IdleMonitor _idle;
    private readonly SessionStateMonitor _session;
    private readonly int _idleThresholdSeconds;

    // State of the currently open (not yet emitted) interval.
    private bool _hasOpen;
    private string _openApp = "";
    private string _openTitle = "";
    private bool _openIdle;
    private bool _openLocked;
    private DateTimeOffset _openStart;
    private DateTimeOffset _openLastPoll;
    private double _openActiveSeconds;

    public ActiveWindowTracker(AppConfig config, IdleMonitor idle, SessionStateMonitor session)
    {
        _idle = idle;
        _session = session;
        _idleThresholdSeconds = config.IdleThresholdSeconds;
    }

    /// <summary>
    /// Sample the current foreground/idle/lock state. Returns a completed
    /// <see cref="ActivityEvent"/> when the sample closed the previous interval,
    /// otherwise null.
    /// </summary>
    public ActivityEvent? Poll()
    {
        var now = DateTimeOffset.UtcNow;
        var (app, title) = ReadForeground();
        int idleSeconds = _idle.GetIdleSeconds();
        bool isIdle = idleSeconds >= _idleThresholdSeconds;
        bool isLocked = _session.IsLocked;

        if (!_hasOpen)
        {
            OpenInterval(app, title, isIdle, isLocked, now);
            return null;
        }

        // Attribute the time since the last poll to the (unchanged) open
        // interval, then decide whether this sample starts a new interval.
        AccrueTo(now);

        bool changed =
            !string.Equals(app, _openApp, StringComparison.Ordinal) ||
            !string.Equals(title, _openTitle, StringComparison.Ordinal) ||
            isIdle != _openIdle ||
            isLocked != _openLocked;

        if (!changed)
        {
            return null;
        }

        var completed = CloseInterval(now);
        OpenInterval(app, title, isIdle, isLocked, now);
        return completed;
    }

    /// <summary>
    /// Close the currently open interval (used on shutdown). Returns the final
    /// event, or null if no interval is open.
    /// </summary>
    public ActivityEvent? FlushCurrent()
    {
        if (!_hasOpen)
        {
            return null;
        }

        var now = DateTimeOffset.UtcNow;
        AccrueTo(now);
        var completed = CloseInterval(now);
        _hasOpen = false;
        return completed;
    }

    private void AccrueTo(DateTimeOffset now)
    {
        double delta = (now - _openLastPoll).TotalSeconds;
        if (delta > 0 && !_openIdle && !_openLocked)
        {
            _openActiveSeconds += delta;
        }
        _openLastPoll = now;
    }

    private void OpenInterval(string app, string title, bool isIdle, bool isLocked, DateTimeOffset now)
    {
        _hasOpen = true;
        _openApp = app;
        _openTitle = title;
        _openIdle = isIdle;
        _openLocked = isLocked;
        _openStart = now;
        _openLastPoll = now;
        _openActiveSeconds = 0;
    }

    private ActivityEvent CloseInterval(DateTimeOffset endedAt)
    {
        return new ActivityEvent
        {
            ClientEventId = Guid.NewGuid().ToString("N"), // 32 hex chars, unique
            Application = _openApp,
            WindowTitle = _openTitle,
            StartedAt = TimeUtil.IsoUtc(_openStart),
            EndedAt = TimeUtil.IsoUtc(endedAt),
            ActiveSeconds = (int)Math.Round(_openActiveSeconds, MidpointRounding.AwayFromZero),
            IsIdle = _openIdle,
            IsLocked = _openLocked,
        };
    }

    /// <summary>Read the foreground app name and window title. Never throws.</summary>
    private static (string App, string Title) ReadForeground()
    {
        IntPtr hwnd = GetForegroundWindow();
        if (hwnd == IntPtr.Zero)
        {
            return ("", "");
        }

        string title = "";
        int len = GetWindowTextLength(hwnd);
        if (len > 0)
        {
            var sb = new StringBuilder(len + 1);
            if (GetWindowText(hwnd, sb, sb.Capacity) > 0)
            {
                title = sb.ToString();
            }
        }

        string app = "";
        if (GetWindowThreadProcessId(hwnd, out uint pid) != 0 && pid != 0)
        {
            try
            {
                using var proc = Process.GetProcessById((int)pid);
                string name = proc.ProcessName; // e.g. "chrome" (no extension)
                app = name.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
                    ? name
                    : name + ".exe"; // normalize to the "chrome.exe" convention
            }
            catch
            {
                // Process may have exited, or access denied for a protected
                // process. We only wanted the name; drop it silently.
                app = "";
            }
        }

        return (app, title);
    }
}
