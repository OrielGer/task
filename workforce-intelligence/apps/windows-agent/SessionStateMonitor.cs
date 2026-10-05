using System.Runtime.Versioning;
using Microsoft.Win32;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Tracks whether the workstation session is locked, via the OS
/// <see cref="SystemEvents.SessionSwitch"/> notification (SessionLock /
/// SessionUnlock). This is pure session-state metadata — no screen or input
/// contents are read.
///
/// SystemEvents maintains its own hidden message-only window on a dedicated
/// background thread, so these notifications are delivered correctly even in a
/// console/worker app with no WinForms/WPF message loop.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class SessionStateMonitor : IDisposable
{
    private volatile bool _isLocked;
    private bool _subscribed;

    /// <summary>True while the session is locked.</summary>
    public bool IsLocked => _isLocked;

    public SessionStateMonitor()
    {
        SystemEvents.SessionSwitch += OnSessionSwitch;
        _subscribed = true;
    }

    private void OnSessionSwitch(object sender, SessionSwitchEventArgs e)
    {
        switch (e.Reason)
        {
            case SessionSwitchReason.SessionLock:
            case SessionSwitchReason.RemoteDisconnect:
                _isLocked = true;
                break;
            case SessionSwitchReason.SessionUnlock:
            case SessionSwitchReason.RemoteConnect:
                _isLocked = false;
                break;
            // Other reasons (logon/logoff/console connect) don't change the
            // locked/unlocked interpretation we care about.
        }
    }

    public void Dispose()
    {
        if (_subscribed)
        {
            try { SystemEvents.SessionSwitch -= OnSessionSwitch; }
            catch { /* ignore teardown races */ }
            _subscribed = false;
        }
    }
}
