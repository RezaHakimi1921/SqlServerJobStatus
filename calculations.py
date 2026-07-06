from datetime import datetime, timedelta

def parse_run_duration(run_duration):
    h = run_duration // 10000
    m = (run_duration % 10000) // 100
    s = run_duration % 100
    return h * 3600 + m * 60 + s

def parse_run_datetime(run_date, run_time):
    try:
        date_str = str(run_date).zfill(8)
        time_str = str(run_time).zfill(6)
        return datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
    except Exception:
        return None

def fmt_seconds(seconds):
    if seconds is None:
        return "-"
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def fmt_duration_hms(seconds):
    if seconds is None:
        return "—"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def job_category(name):
    if "." in name:
        parts = name.split(".", 1)
        suffix = parts[1].split("_")[0] if "_" in parts[1] else parts[1][:12]
        return f"{parts[0]} / {suffix}"
    if "_" in name:
        parts = name.split("_")
        if len(parts) >= 2:
            return f"{parts[0]} / {parts[1]}"
        return parts[0]
    return "General"


GANTT_DAY_MINUTES = 24 * 60
RUN_STATUS_GANTT = {0: "error", 1: "success", 2: "failed", 3: "idle"}
GANTT_STATUS_PRIORITY = {"running": 4, "error": 3, "failed": 2, "success": 1, "idle": 0}


def _dt_to_minutes(dt):
    if not dt:
        return 0
    return dt.hour * 60 + dt.minute + dt.second / 60.0


def _format_hm(dt):
    if not dt:
        return "—"
    return dt.strftime("%H:%M")


def build_gantt_rows(today_runs_raw, running_jobs, job_stats):
    """Build Gantt rows with ALL today's executions per job (00:00–23:59)."""
    from datetime import timedelta

    today = datetime.now().date()
    now = datetime.now()
    now_min = _dt_to_minutes(now)

    rows = {}

    def ensure_row(job_id, name):
        if job_id not in rows:
            rows[job_id] = {
                "job_id": job_id,
                "name": name,
                "bars": [],
                "row_status": "idle",
            }
        return rows[job_id]

    def add_bar(row, start_dt, end_dt, status, progress=100):
        if start_dt.date() != today:
            return
        start_min = _dt_to_minutes(start_dt)
        end_min = min(_dt_to_minutes(end_dt), GANTT_DAY_MINUTES)
        if end_min <= start_min:
            end_min = min(start_min + 1, GANTT_DAY_MINUTES)
        row["bars"].append({
            "start_min": start_min,
            "end_min": end_min,
            "status": status,
            "progress": min(100, max(0, int(progress or 0))),
            "start_str": _format_hm(start_dt),
            "end_str": _format_hm(end_dt) if status != "running" else "الان",
            "duration_str": fmt_duration_hms((end_min - start_min) * 60),
        })
        pri = GANTT_STATUS_PRIORITY.get(status, 0)
        if pri > GANTT_STATUS_PRIORITY.get(row["row_status"], 0):
            row["row_status"] = status

    for h in today_runs_raw:
        jid = h["job_id"]
        name = h["name"]
        start_dt = h.get("start_dt") or parse_run_datetime(h["run_date"], h["run_time"])
        if h.get("end_dt"):
            end_dt = h["end_dt"]
        elif start_dt:
            dur = h.get("duration_seconds")
            if dur is None:
                dur = parse_run_duration(h["run_duration"])
            end_dt = start_dt + timedelta(seconds=dur)
        else:
            end_dt = None
        status = RUN_STATUS_GANTT.get(h["run_status"], "idle")
        row = ensure_row(jid, name)
        add_bar(row, start_dt, end_dt or start_dt, status, 100)

    for r in running_jobs:
        jid = r["job_id"]
        start = r.get("start_dt")
        if not start or start.date() != today:
            continue
        pct, _, _, _ = calc_progress(jid, start, job_stats)
        row = ensure_row(jid, r["name"])
        add_bar(row, start, now, "running", pct if pct is not None else 0)

    result = []
    for row in rows.values():
        if not row["bars"]:
            continue
        row["bars"].sort(key=lambda b: b["start_min"])
        result.append(row)
    result.sort(key=lambda r: r["name"].lower())
    return result

def enrich_history(history_raw):
    """Add start_dt, duration_seconds, end_dt to each history row."""
    enriched = []
    for h in history_raw:
        row = dict(h)
        dt = parse_run_datetime(h["run_date"], h["run_time"])
        dur = parse_run_duration(h["run_duration"])
        row["start_dt"] = dt
        row["duration_seconds"] = dur
        row["end_dt"] = (dt + timedelta(seconds=dur)) if dt else None
        enriched.append(row)
    return enriched

def calc_job_stats(history):
    """Per-job average duration from successful runs."""
    stats = {}
    for h in history:
        if h["run_status"] != 1:
            continue
        jid = h["job_id"]
        dur = h["duration_seconds"]
        if jid not in stats:
            stats[jid] = {"total": 0, "count": 0}
        stats[jid]["total"] += dur
        stats[jid]["count"] += 1
    return {jid: v["total"] / v["count"] for jid, v in stats.items() if v["count"] > 0}

def calc_progress(job_id, start_dt, job_stats):
    if start_dt is None:
        return None, None, False, False
    elapsed = (datetime.now() - start_dt).total_seconds()
    avg = job_stats.get(job_id)
    if not avg:
        return None, None, False, False
    pct = min(int(elapsed / avg * 100), 99)
    remaining = max(0, avg - elapsed)
    is_slow = elapsed > avg * 1.1
    is_very_slow = elapsed > avg * 1.5
    return pct, remaining, is_slow, is_very_slow
