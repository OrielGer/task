using System.Runtime.InteropServices;
using System.Runtime.Versioning;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Reports how long it has been since the last user input.
///
/// IMPORTANT: this measures the *time since* the last keyboard/mouse input
/// only. It does NOT read, capture, or log which keys were pressed or what was
/// typed. Win32 GetLastInputInfo returns a tick count, nothing more.
/// </summary>
[SupportedOSPlatform("windows")]
public sealed class IdleMonitor
{
    [StructLayout(LayoutKind.Sequential)]
    private struct LASTINPUTINFO
    {
        public uint cbSize;
        public uint dwTime; // tick count of the last input event (GetTickCount)
    }

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    /// <summary>Seconds elapsed since the last keyboard or mouse input.</summary>
    public int GetIdleSeconds()
    {
        var lii = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
        if (!GetLastInputInfo(ref lii))
        {
            return 0;
        }

        // GetTickCount wraps roughly every 49.7 days; unchecked unsigned
        // subtraction gives the correct delta across the wrap boundary.
        uint nowTicks = unchecked((uint)Environment.TickCount);
        uint idleMs = unchecked(nowTicks - lii.dwTime);
        return (int)(idleMs / 1000u);
    }
}
