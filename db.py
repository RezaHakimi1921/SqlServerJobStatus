import time

import pyodbc

from config import build_conn_str, is_configured, load_config

HISTORY_DAYS = 1
STATS_RUNS_PER_JOB = 5
GANTT_RUNS_PER_JOB = 24
_BATCH_CACHE = {"ts": 0.0, "data": None}
_BATCH_CACHE_TTL = 8


def get_connection(config=None):
    cfg = config or load_config()
    timeout = cfg.get("timeout", 15)
    return pyodbc.connect(build_conn_str(cfg), timeout=timeout)


def rows_to_dicts(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def _duration_seconds(run_duration):
    if run_duration is None:
        return 0
    v = int(run_duration)
    return (v // 10000) * 3600 + ((v % 10000) // 100) * 60 + (v % 100)


def get_running_jobs():
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SET NOCOUNT ON;
            SELECT
                CONVERT(VARCHAR(36), ja.job_id) AS job_id,
                j.name,
                ja.start_execution_date AS start_dt
            FROM msdb.dbo.sysjobactivity ja
            INNER JOIN msdb.dbo.sysjobs j ON j.job_id = ja.job_id
            WHERE ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.sysjobactivity)
              AND ja.start_execution_date IS NOT NULL
              AND ja.stop_execution_date IS NULL
        """)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def get_dashboard_batch(use_cache=True):
    """Optimized batch: no duplicate running query, minimal columns, SQL-side aggregation."""
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")

    now = time.time()
    if use_cache and _BATCH_CACHE["data"] and (now - _BATCH_CACHE["ts"]) < _BATCH_CACHE_TTL:
        return _BATCH_CACHE["data"]

    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT CONVERT(VARCHAR(36), job_id) AS job_id, name, enabled
            FROM msdb.dbo.sysjobs ORDER BY name
        """)
        all_jobs = rows_to_dicts(cur)
        for r in all_jobs:
            r["enabled"] = bool(r["enabled"])

        cur.execute("""
            DECLARE @since INT = CONVERT(
                INT, CONVERT(VARCHAR(8), DATEADD(day, ?, GETDATE()), 112)
            );
            WITH latest AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    j.name,
                    jh.run_date, jh.run_time, jh.run_duration, jh.run_status,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id
                        ORDER BY jh.run_date DESC, jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
                WHERE jh.step_id = 0 AND jh.run_date >= @since
            )
            SELECT job_id, name, run_date, run_time, run_duration, run_status
            FROM latest WHERE rn = 1
        """, -HISTORY_DAYS)
        latest_runs = rows_to_dicts(cur)
        for r in latest_runs:
            r["duration_seconds"] = _duration_seconds(r.get("run_duration"))

        cur.execute("""
            DECLARE @since INT = CONVERT(
                INT, CONVERT(VARCHAR(8), DATEADD(day, ?, GETDATE()), 112)
            );
            WITH succ AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    jh.run_duration,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id
                        ORDER BY jh.run_date DESC, jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                WHERE jh.step_id = 0 AND jh.run_status = 1 AND jh.run_date >= @since
            )
            SELECT job_id,
                   AVG(
                       (run_duration / 10000) * 3600
                       + ((run_duration % 10000) / 100) * 60
                       + (run_duration % 100)
                   ) AS avg_seconds
            FROM succ WHERE rn <= ?
            GROUP BY job_id
        """, -HISTORY_DAYS, STATS_RUNS_PER_JOB)
        job_stats = {
            r["job_id"]: float(r["avg_seconds"])
            for r in rows_to_dicts(cur)
            if r.get("avg_seconds") is not None
        }

        cur.execute("""
            DECLARE @today INT = CONVERT(INT, CONVERT(VARCHAR(8), GETDATE(), 112));
            WITH today_r AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    j.name,
                    jh.run_date, jh.run_time, jh.run_duration, jh.run_status,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id ORDER BY jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
                WHERE jh.step_id = 0 AND jh.run_date = @today
            )
            SELECT job_id, name, run_date, run_time, run_duration, run_status
            FROM today_r WHERE rn <= ?
            ORDER BY name, run_time
        """, GANTT_RUNS_PER_JOB)
        today_runs = rows_to_dicts(cur)
        for r in today_runs:
            r["duration_seconds"] = _duration_seconds(r.get("run_duration"))

        cur.execute("""
            DECLARE @today INT = CONVERT(INT, CONVERT(VARCHAR(8), GETDATE(), 112));
            SELECT TOP 50
                CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                j.name, jh.step_id, jh.step_name,
                LEFT(jh.message, 500) AS message,
                jh.run_date, jh.run_time
            FROM msdb.dbo.sysjobhistory jh
            INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
            WHERE jh.run_status = 0 AND jh.run_date = @today AND jh.step_id > 0
            ORDER BY jh.run_date DESC, jh.run_time DESC
        """)
        today_failures = rows_to_dicts(cur)

        cur.execute("""
            DECLARE @since INT = CONVERT(
                INT, CONVERT(VARCHAR(8), DATEADD(day, ?, GETDATE()), 112)
            );
            WITH fails AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    j.name, jh.step_name,
                    LEFT(jh.message, 500) AS message,
                    jh.run_date, jh.run_time,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id
                        ORDER BY jh.run_date DESC, jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
                WHERE jh.run_status = 0 AND jh.step_id > 0 AND jh.run_date >= @since
            )
            SELECT job_id, name, step_name, message, run_date, run_time
            FROM fails WHERE rn = 1
        """, -HISTORY_DAYS)
        latest_failures = rows_to_dicts(cur)

        result = (latest_runs, all_jobs, job_stats, today_runs, today_failures, latest_failures)
        _BATCH_CACHE["ts"] = now
        _BATCH_CACHE["data"] = result
        return result
    finally:
        conn.close()


def invalidate_batch_cache():
    _BATCH_CACHE["ts"] = 0.0
    _BATCH_CACHE["data"] = None


def get_job_history(days=HISTORY_DAYS, per_job=STATS_RUNS_PER_JOB):
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SET NOCOUNT ON;
            DECLARE @since INT = CONVERT(
                INT, CONVERT(VARCHAR(8), DATEADD(day, ?, GETDATE()), 112)
            );
            WITH ranked AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    j.name,
                    jh.run_date, jh.run_time, jh.run_duration,
                    jh.run_status, jh.message,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id
                        ORDER BY jh.run_date DESC, jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
                WHERE jh.step_id = 0 AND jh.run_date >= @since
            )
            SELECT job_id, name, run_date, run_time, run_duration, run_status, message
            FROM ranked WHERE rn <= ?
            ORDER BY run_date DESC, run_time DESC
        """, -days, per_job)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def get_all_jobs():
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT CONVERT(VARCHAR(36), job_id) AS job_id, name, enabled
            FROM msdb.dbo.sysjobs ORDER BY name
        """)
        rows = rows_to_dicts(cur)
        for r in rows:
            r["enabled"] = bool(r["enabled"])
        return rows
    finally:
        conn.close()


def get_today_runs():
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SET NOCOUNT ON;
            DECLARE @today INT = CONVERT(INT, CONVERT(VARCHAR(8), GETDATE(), 112));
            WITH ranked AS (
                SELECT
                    CONVERT(VARCHAR(36), jh.job_id) AS job_id,
                    j.name,
                    jh.run_date, jh.run_time, jh.run_duration, jh.run_status,
                    ROW_NUMBER() OVER (
                        PARTITION BY jh.job_id ORDER BY jh.run_time DESC
                    ) AS rn
                FROM msdb.dbo.sysjobhistory jh
                INNER JOIN msdb.dbo.sysjobs j ON j.job_id = jh.job_id
                WHERE jh.step_id = 0 AND jh.run_date = @today
            )
            SELECT job_id, name, run_date, run_time, run_duration, run_status
            FROM ranked WHERE rn <= ?
            ORDER BY name, run_time
        """, GANTT_RUNS_PER_JOB)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def get_job_step_definitions(job_id: str):
    """Job step/SP definitions from sysjobsteps (works for inactive jobs)."""
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                js.step_id,
                js.step_name,
                js.subsystem,
                LEFT(js.command, 200) AS command_preview
            FROM msdb.dbo.sysjobsteps js
            WHERE js.job_id = CONVERT(UNIQUEIDENTIFIER, ?)
            ORDER BY js.step_id
        """, job_id)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def get_step_runs_grouped(job_id: str, max_runs=20, since_days=None):
    """Step history grouped by job execution (step_id=0 outcome rows).

    instance_id is unique per ROW in sysjobhistory — step rows do NOT share the
    job-outcome instance_id. Steps for a run have lower instance_id values than
    their step_id=0 outcome row; we group by instance_id range between outcomes.
    """
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    n = max(1, min(int(max_runs), 100))
    conn = get_connection()
    try:
        cur = conn.cursor()
        since_clause = ""
        params = [job_id]
        if since_days is not None:
            since_clause = "AND run_date >= CONVERT(INT, CONVERT(VARCHAR(8), DATEADD(day, ?, GETDATE()), 112))"
            params.append(-int(since_days))

        cur.execute(f"""
            DECLARE @job UNIQUEIDENTIFIER = CONVERT(UNIQUEIDENTIFIER, ?);
            WITH outcomes AS (
                SELECT
                    instance_id AS outcome_instance_id,
                    run_date AS job_run_date,
                    run_time AS job_run_time,
                    run_status AS job_run_status,
                    run_duration AS job_run_duration,
                    ROW_NUMBER() OVER (ORDER BY run_date DESC, run_time DESC) AS rn
                FROM msdb.dbo.sysjobhistory
                WHERE job_id = @job
                  AND step_id = 0
                  {since_clause}
            ),
            recent AS (
                SELECT outcome_instance_id, job_run_date, job_run_time,
                       job_run_status, job_run_duration
                FROM outcomes
                WHERE rn <= {n}
            )
            SELECT
                r.outcome_instance_id AS instance_id,
                r.job_run_date,
                r.job_run_time,
                r.job_run_status,
                r.job_run_duration,
                jh.step_id,
                jh.step_name,
                jh.run_duration,
                jh.run_status,
                LEFT(jh.message, 400) AS message
            FROM recent r
            INNER JOIN msdb.dbo.sysjobhistory jh
                ON jh.job_id = @job
               AND jh.step_id > 0
               AND jh.instance_id < r.outcome_instance_id
               AND jh.instance_id > COALESCE((
                    SELECT MAX(o2.outcome_instance_id)
                    FROM outcomes o2
                    WHERE o2.outcome_instance_id < r.outcome_instance_id
                ), 0)
            ORDER BY r.job_run_date DESC, r.job_run_time DESC, jh.step_id ASC
        """, *params)
        return rows_to_dicts(cur)
    finally:
        conn.close()


def get_step_history(job_id: str, limit=40):
    if not is_configured():
        raise RuntimeError("اتصال SQL Server پیکربندی نشده است.")
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            SET NOCOUNT ON;
            SELECT TOP {int(limit)}
                jh.step_id,
                jh.step_name,
                jh.run_date,
                jh.run_time,
                jh.run_duration,
                jh.run_status,
                LEFT(jh.message, 1000) AS message
            FROM msdb.dbo.sysjobhistory jh
            WHERE jh.job_id = CONVERT(UNIQUEIDENTIFIER, ?)
              AND jh.step_id > 0
              AND jh.run_date >= CONVERT(
                    INT,
                    CONVERT(VARCHAR(8), DATEADD(day, -3, GETDATE()), 112)
                  )
            ORDER BY jh.run_date DESC, jh.run_time DESC
        """, job_id)
        return rows_to_dicts(cur)
    finally:
        conn.close()
