using Microsoft.Data.Sqlite;

namespace WorkforceIntelligence.Agent;

/// <summary>
/// Durable local buffer for activity events, backed by SQLite. Events are
/// enqueued as they close and removed only after the backend acknowledges them
/// (HTTP 2xx). This lets telemetry survive a backend outage or a restart.
///
/// A single long-lived connection is used, guarded by a lock because the poll
/// loop and the flush path can touch it from the same async pump.
/// </summary>
public sealed class EventBuffer : IDisposable
{
    private readonly SqliteConnection _conn;
    private readonly object _gate = new();

    public EventBuffer(string sqlitePath)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(sqlitePath));
        if (!string.IsNullOrEmpty(dir))
        {
            Directory.CreateDirectory(dir);
        }

        _conn = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = sqlitePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
        }.ToString());
        _conn.Open();

        using var pragma = _conn.CreateCommand();
        // WAL keeps buffered data intact if the process is killed mid-write.
        pragma.CommandText = "PRAGMA journal_mode=WAL;";
        pragma.ExecuteNonQuery();

        using var create = _conn.CreateCommand();
        create.CommandText = @"
            CREATE TABLE IF NOT EXISTS activity_events (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                client_event_id TEXT NOT NULL UNIQUE,
                application     TEXT NOT NULL,
                window_title    TEXT NOT NULL,
                started_at      TEXT NOT NULL,
                ended_at        TEXT NOT NULL,
                active_seconds  INTEGER NOT NULL,
                is_idle         INTEGER NOT NULL,
                is_locked       INTEGER NOT NULL,
                created_at      TEXT NOT NULL
            );";
        create.ExecuteNonQuery();
    }

    /// <summary>Add one event. Duplicate client_event_ids are ignored.</summary>
    public void Enqueue(ActivityEvent e)
    {
        lock (_gate)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                INSERT OR IGNORE INTO activity_events
                    (client_event_id, application, window_title, started_at,
                     ended_at, active_seconds, is_idle, is_locked, created_at)
                VALUES ($cid, $app, $title, $start, $end, $active, $idle, $locked, $created);";
            cmd.Parameters.AddWithValue("$cid", e.ClientEventId);
            cmd.Parameters.AddWithValue("$app", e.Application);
            cmd.Parameters.AddWithValue("$title", e.WindowTitle);
            cmd.Parameters.AddWithValue("$start", e.StartedAt);
            cmd.Parameters.AddWithValue("$end", e.EndedAt);
            cmd.Parameters.AddWithValue("$active", e.ActiveSeconds);
            cmd.Parameters.AddWithValue("$idle", e.IsIdle ? 1 : 0);
            cmd.Parameters.AddWithValue("$locked", e.IsLocked ? 1 : 0);
            cmd.Parameters.AddWithValue("$created", TimeUtil.IsoUtc(DateTimeOffset.UtcNow));
            cmd.ExecuteNonQuery();
        }
    }

    /// <summary>Read up to <paramref name="max"/> oldest events (FIFO by id).</summary>
    public List<(long Id, ActivityEvent Event)> DequeueBatch(int max)
    {
        var batch = new List<(long, ActivityEvent)>(Math.Max(0, max));
        lock (_gate)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = @"
                SELECT id, client_event_id, application, window_title, started_at,
                       ended_at, active_seconds, is_idle, is_locked
                FROM activity_events
                ORDER BY id
                LIMIT $max;";
            cmd.Parameters.AddWithValue("$max", max);

            using var reader = cmd.ExecuteReader();
            while (reader.Read())
            {
                long id = reader.GetInt64(0);
                var ev = new ActivityEvent
                {
                    ClientEventId = reader.GetString(1),
                    Application = reader.GetString(2),
                    WindowTitle = reader.GetString(3),
                    StartedAt = reader.GetString(4),
                    EndedAt = reader.GetString(5),
                    ActiveSeconds = reader.GetInt32(6),
                    IsIdle = reader.GetInt32(7) != 0,
                    IsLocked = reader.GetInt32(8) != 0,
                };
                batch.Add((id, ev));
            }
        }
        return batch;
    }

    /// <summary>Delete rows the backend has acknowledged.</summary>
    public void DeleteAcked(IEnumerable<long> ids)
    {
        var idList = ids as IList<long> ?? ids.ToList();
        if (idList.Count == 0)
        {
            return;
        }

        lock (_gate)
        {
            using var cmd = _conn.CreateCommand();
            var names = new string[idList.Count];
            for (int i = 0; i < idList.Count; i++)
            {
                names[i] = "$id" + i;
                cmd.Parameters.AddWithValue(names[i], idList[i]);
            }
            cmd.CommandText = $"DELETE FROM activity_events WHERE id IN ({string.Join(",", names)});";
            cmd.ExecuteNonQuery();
        }
    }

    /// <summary>Number of buffered events awaiting upload.</summary>
    public long Count()
    {
        lock (_gate)
        {
            using var cmd = _conn.CreateCommand();
            cmd.CommandText = "SELECT COUNT(*) FROM activity_events;";
            var result = cmd.ExecuteScalar();
            return result is long l ? l : Convert.ToInt64(result);
        }
    }

    public void Dispose()
    {
        lock (_gate)
        {
            _conn.Dispose();
        }
        // Release pooled handles so the WAL/-shm files settle on shutdown.
        SqliteConnection.ClearAllPools();
    }
}
