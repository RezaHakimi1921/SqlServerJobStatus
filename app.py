import math
import os
from datetime import datetime, timedelta

import dash
from dash import dcc, html, Input, Output, State, ALL, ctx
from dotenv import load_dotenv

load_dotenv()

from flask import request

from config import (
    is_configured, load_config, resolve_password, save_config,
    save_refresh_minutes, test_connection, list_sql_driver_options,
)
from db import (
    get_running_jobs, get_dashboard_batch,
    get_step_runs_grouped, get_job_step_definitions, invalidate_batch_cache,
)
from calculations import (
    calc_progress, build_gantt_rows,
    fmt_duration_hms, job_category, parse_run_datetime, parse_run_duration, fmt_seconds,
    GANTT_DAY_MINUTES,
)

REFRESH_OPTIONS = [
    {"label": "1 دقیقه", "value": "1"},
    {"label": "5 دقیقه", "value": "5"},
    {"label": "10 دقیقه", "value": "10"},
    {"label": "30 دقیقه", "value": "30"},
    {"label": "60 دقیقه", "value": "60"},
]

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
_VALID_REFRESH = frozenset({1, 5, 10, 30, 60})

_cfg = load_config()
REFRESH_MINUTES = _cfg.get("refresh_minutes", 5)
DASH_HOST = os.getenv("DASH_HOST", "127.0.0.1")
DASH_PORT = int(os.getenv("DASH_PORT", "8050"))
PAGE_SIZE = 15
GANTT_HOURS = 24
GANTT_BASE_CELL = 90

STATUS_UI = {
    "running": "در حال اجرا",
    "error": "خطا",
    "success": "موفق",
    "failed": "شکست‌خورده",
    "idle": "غیرفعال",
}

ICONS = {
    "cog": "⚙", "bell": "🔔", "close": "✕", "refresh": "↻",
    "list": "☰", "gantt": "▥", "report": "📄", "search": "🔍",
    "dots": "⋮", "clock": "⏱", "play": "▶", "warn": "⚠",
    "ok": "✓", "fail": "✗", "pause": "⏸", "shield": "🛡",
    "zoom-in": "+", "zoom-out": "−", "chev-r": "›", "chev-l": "‹",
    "db": "🗄", "pause": "⏸", "play": "▶", "snapshot": "📷",
}


def Ico(name, extra_class=""):
    cls = "ico" + (f" {extra_class}" if extra_class else "")
    return html.Span(ICONS.get(name, "•"), className=cls, **{"aria-hidden": "true"})

app = dash.Dash(__name__, suppress_callback_exceptions=True, title="Data Agent Monitor")
app.title = "Data Agent Monitor"

app.index_string = """<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@200;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
</head>
<body>
    {%app_entry%}
    <footer>{%config%}{%scripts%}{%renderer%}</footer>
    <script src="/assets/gantt.js"></script>
</body>
</html>"""


def _serialize_rows(rows):
    def dt_str(v):
        return v.isoformat() if isinstance(v, datetime) else v
    return [{k: dt_str(v) for k, v in r.items()} for r in rows]


def _parse_dt(s):
    if s and isinstance(s, str):
        try:
            return datetime.fromisoformat(s)
        except Exception:
            return None
    return s


def _enrich_run_row(h):
    row = dict(h)
    dt = parse_run_datetime(h["run_date"], h["run_time"])
    dur = h.get("duration_seconds")
    if dur is None:
        dur = parse_run_duration(h.get("run_duration") or 0)
    row["start_dt"] = dt
    row["duration_seconds"] = dur
    row["end_dt"] = (dt + timedelta(seconds=dur)) if dt else None
    return row


def build_jobs_overview(all_jobs, running, latest_runs, job_stats, failure_map=None):
    failure_map = failure_map or {}
    running_map = {r["job_id"]: r for r in running}
    latest = {h["job_id"]: h for h in latest_runs}

    overview = []
    for j in all_jobs:
        jid = j["job_id"]
        name = j["name"]
        cat = job_category(name)

        if jid in running_map:
            start = running_map[jid].get("start_dt")
            pct, _, _, _ = calc_progress(jid, start, job_stats)
            elapsed = (datetime.now() - start).total_seconds() if start else 0
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "running", "progress": pct if pct is not None else 0,
                "duration": fmt_duration_hms(elapsed),
                "nextRun": "—", "steps": "در حال اجرا",
            })
        elif not j.get("enabled", True):
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "idle", "progress": 0,
                "duration": "—", "nextRun": "—", "steps": "غیرفعال",
            })
        elif jid in latest:
            h = latest[jid]
            rs = h["run_status"]
            status = {0: "error", 1: "success", 2: "failed", 3: "idle"}.get(rs, "idle")
            progress = 100 if rs == 1 else (0 if rs == 0 else 78)
            fail = failure_map.get(jid, {})
            msg = fail.get("message") or h.get("message") or ""
            step = fail.get("step_name") or ""
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": status, "progress": progress,
                "duration": fmt_duration_hms(h.get("duration_seconds")),
                "nextRun": "—",
                "steps": (msg[:80] if msg else STATUS_UI.get(status, "")),
                "failedStep": step,
                "errorMessage": msg,
            })
        else:
            overview.append({
                "job_id": jid, "name": name, "category": cat,
                "status": "idle", "progress": 0,
                "duration": "—", "nextRun": "—", "steps": "بدون سابقه",
            })
    return overview


def _native_select(select_id, options, value, className="form-input native-select"):
    """Dark-themed native select matching app palette."""
    str_val = str(value) if value is not None else ""
    return html.Select(
        id=select_id,
        className=className,
        children=[
            html.Option(
                opt["label"],
                value=str(opt["value"]),
                selected=(str(opt["value"]) == str_val),
            )
            for opt in options
        ],
    )


def _parse_refresh_minutes(raw):
    """Parse refresh interval from select value or Persian label like '۱۰ دقیقه'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip().translate(_PERSIAN_DIGITS)
    if s.isdigit():
        return int(s)
    import re
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _run_status_duration_line(status_key, status_label, total_sec, *, compact=False):
    """Single-line status + duration with explicit labels."""
    dur = fmt_duration_hms(total_sec)
    unit = "" if compact else html.Span(" (ساعت:دقیقه:ثانیه)", className="dur-unit")
    return html.Div(className="run-status-dur-line", children=[
        html.Span("وضعیت:", className="meta-lbl"),
        html.Span(status_label, className=f"meta-status status-{status_key}"),
        html.Span("|", className="meta-sep", **{"aria-hidden": "true"}),
        html.Span("مدت اجرا:", className="meta-lbl"),
        html.Span(dur, className="meta-dur"),
        unit,
    ])


def _parse_grouped_runs(grouped_rows):
    """Parse SQL rows into ordered list of run dicts with steps."""
    runs_map = {}
    run_order = []
    for row in grouped_rows or []:
        iid = row["instance_id"]
        if iid not in runs_map:
            dt = parse_run_datetime(row["job_run_date"], row["job_run_time"])
            job_st = row.get("job_run_status", 1)
            status_key = {0: "error", 1: "success", 2: "failed", 3: "idle"}.get(job_st, "idle")
            job_dur = parse_run_duration(row.get("job_run_duration") or 0)
            runs_map[iid] = {
                "dt": dt, "status_key": status_key, "job_dur": job_dur, "steps": [],
            }
            run_order.append(iid)
        runs_map[iid]["steps"].append(row)
        if row.get("run_status") == 0:
            runs_map[iid]["status_key"] = "error"
    return [runs_map[iid] for iid in run_order]


def _run_total_seconds(run):
    if run.get("job_dur"):
        return run["job_dur"]
    return sum(parse_run_duration(s.get("run_duration") or 0) for s in run.get("steps", []))


def _build_job_summary_card(job_info, latest_run):
    status = job_info.get("status", "idle")
    st_label = STATUS_UI.get(status, status)
    last_dt = "—"
    last_dur = job_info.get("duration", "—")
    n_steps = "—"
    run_status = "—"

    if latest_run:
        dt = latest_run.get("dt")
        last_dt = dt.strftime("%Y/%m/%d  %H:%M:%S") if dt else "—"
        total_sec = _run_total_seconds(latest_run)
        last_dur = fmt_duration_hms(total_sec) if total_sec else "—"
        n_steps = str(len(latest_run.get("steps", [])))
        run_status = STATUS_UI.get(latest_run.get("status_key"), "—")

    return html.Div(className="job-summary-card", children=[
        html.Div("خلاصه جاب", className="job-summary-title"),
        html.Div(className="job-summary-grid", children=[
            html.Div([
                html.Span("وضعیت فعلی", className="job-summary-lbl"),
                html.Span(st_label, className=f"job-summary-val status-{status}"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("آخرین اجرا", className="job-summary-lbl"),
                html.Span(last_dt, className="job-summary-val"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("مدت کل جاب", className="job-summary-lbl"),
                html.Span(last_dur, className="job-summary-val dur"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("نتیجه آخرین اجرا", className="job-summary-lbl"),
                html.Span(run_status, className="job-summary-val"),
            ], className="job-summary-item"),
            html.Div([
                html.Span("تعداد Step", className="job-summary-lbl"),
                html.Span(n_steps, className="job-summary-val"),
            ], className="job-summary-item"),
        ]),
    ])


def _build_step_rows_table(steps, show_message=False):
    status_labels = {0: "ناموفق", 1: "موفق", 2: "تلاش مجدد", 3: "لغو"}
    rows = []
    for s in steps:
        dur = parse_run_duration(s.get("run_duration") or 0)
        st = s.get("run_status", 1)
        row_cls = "step-failed" if st == 0 else ""
        msg = (s.get("message") or "").strip()
        cells = [
            html.Td(str(s["step_id"]), className=f"col-step {row_cls}"),
            html.Td(s["step_name"], className=f"col-name {row_cls}", title=s["step_name"]),
            html.Td(
                html.Div(className="step-result-line", children=[
                    html.Span(status_labels.get(st, "?"), className=f"step-status {row_cls}"),
                    html.Span("·", className="step-sep", **{"aria-hidden": "true"}),
                    html.Span(fmt_duration_hms(dur), className="step-dur", title="ساعت:دقیقه:ثانیه"),
                ]),
                className=f"col-result {row_cls}",
            ),
        ]
        if show_message:
            cells.append(html.Td(
                (msg[:80] + "…") if len(msg) > 80 else (msg or "—"),
                className=f"col-msg {row_cls}", title=msg,
            ))
        rows.append(html.Tr(cells))
    headers = [
        html.Th("#", className="col-step"),
        html.Th("نام Step / SP", className="col-name"),
        html.Th("وضعیت / مدت (ساعت:دقیقه:ثانیه)", className="col-result"),
    ]
    if show_message:
        headers.append(html.Th("پیام", className="col-msg"))
    return html.Table(className="detail-table run-steps-table", children=[
        html.Thead(html.Tr(headers)),
        html.Tbody(rows),
    ])


def _build_latest_run_section(latest_run):
    if not latest_run or not latest_run.get("steps"):
        return None
    dt = latest_run.get("dt")
    dt_label = dt.strftime("%Y/%m/%d  %H:%M:%S") if dt else "—"
    total_sec = _run_total_seconds(latest_run)
    st_label = STATUS_UI.get(latest_run.get("status_key"), "—")
    return html.Div(className="latest-run-section", children=[
        html.Div(className="job-def-title", children=[
            html.Span("▶", className="ico"),
            " آخرین اجرا — جزئیات هر Step",
            html.Span(f" ({dt_label})", className="job-def-count"),
        ]),
        html.Div(className="latest-run-meta", children=[
            _run_status_duration_line(
                latest_run.get("status_key", "idle"), st_label, total_sec,
            ),
        ]),
        _build_step_rows_table(latest_run["steps"], show_message=True),
    ])


def _build_job_definition_section(definitions, latest_run=None):
    if not definitions:
        return None
    last_step_map = {}
    if latest_run:
        for s in latest_run.get("steps", []):
            last_step_map[s["step_id"]] = s

    rows = []
    for d in definitions:
        sub = d.get("subsystem") or "—"
        sid = d["step_id"]
        last = last_step_map.get(sid)
        if last:
            dur = fmt_duration_hms(parse_run_duration(last.get("run_duration") or 0))
            st = {0: "ناموفق", 1: "موفق", 2: "تلاش مجدد", 3: "لغو"}.get(last.get("run_status", 1), "—")
            result_cell = html.Td(
                html.Div(className="step-result-line", children=[
                    html.Span(st, className="step-status"),
                    html.Span("·", className="step-sep", **{"aria-hidden": "true"}),
                    html.Span(dur, className="step-dur", title="ساعت:دقیقه:ثانیه"),
                ]),
                className="col-result",
            )
        else:
            result_cell = html.Td("—", className="col-result muted")
        rows.append(html.Tr([
            html.Td(str(sid), className="col-step"),
            html.Td(d["step_name"], className="col-name", title=d["step_name"]),
            html.Td(sub, className="col-subsystem"),
            result_cell,
        ]))
    return html.Div(className="job-def-section", children=[
        html.Div(className="job-def-title", children=[
            html.Span("📋", className="ico"),
            " تعریف جاب — Steps / SPها",
            html.Span(f" ({len(definitions)} مرحله)", className="job-def-count"),
        ]),
        html.Table(className="detail-table job-def-table", children=[
            html.Thead(html.Tr([
                html.Th("#", className="col-step"),
                html.Th("نام Step / SP", className="col-name"),
                html.Th("نوع", className="col-subsystem"),
                html.Th("آخرین وضعیت / مدت (ساعت:دقیقه:ثانیه)", className="col-result"),
            ])),
            html.Tbody(rows),
        ]),
    ])


def _build_grouped_runs_section(runs_list, empty_ok=False):
    """Older runs list. If empty_ok=True, return None instead of empty message."""
    if not runs_list:
        if empty_ok:
            return None
        return html.Div(className="run-history-section", children=[
            html.Div(className="job-def-title", children=[
                html.Span("🕐", className="ico"), " تاریخچه اجراهای قبلی",
            ]),
            html.P(
                "سابقه اجرا در msdb یافت نشد — ممکن است history پاک شده یا جاب هنوز اجرا نشده باشد.",
                className="history-empty-hint",
            ),
        ])

    status_labels = {0: "ناموفق", 1: "موفق", 2: "تلاش مجدد", 3: "لغو"}
    run_blocks = []
    total = len(runs_list)

    for idx, run in enumerate(runs_list):
        dt = run["dt"]
        dt_label = dt.strftime("%Y/%m/%d  %H:%M:%S") if dt else "—"
        n_steps = len(run["steps"])
        st_label = STATUS_UI.get(run["status_key"], run["status_key"])
        total_dur = _run_total_seconds(run)

        summary = html.Div(className="run-summary-line", children=[
            html.Span(f"اجرای {total - idx}", className="run-instance-num"),
            html.Span(dt_label, className="run-instance-time"),
            _run_status_duration_line(run["status_key"], st_label, total_dur, compact=True),
            html.Span(f"{n_steps} Step", className="run-summary-steps"),
        ])

        run_blocks.append(html.Details(
            className="run-instance",
            open=False,
            children=[
                html.Summary(className="run-instance-summary", children=[summary]),
                _build_step_rows_table(run["steps"], show_message=True),
            ],
        ))

    return html.Div(className="run-history-section", children=[
        html.Div(className="job-def-title", children=[
            html.Span("🕐", className="ico"),
            " تاریخچه اجراهای قبلی",
            html.Span(f" ({total} اجرا)", className="job-def-count"),
        ]),
        html.P(
            "روی هر اجرا کلیک کنید — مدت هر Step/SP نمایش داده می‌شود.",
            className="history-hint",
        ),
        html.Div(className="run-instances-list", children=run_blocks),
    ])


def _settings_modal(open_by_default=False):
    cfg = load_config()
    hidden = "" if open_by_default else " hidden"
    return html.Div(
        id="settings-modal",
        className=f"modal-overlay{hidden}",
        children=[
            html.Div(className="modal-content modal-settings", children=[
                html.Div(className="modal-header", children=[
                    html.H2([Ico("cog"), " تنظیمات"]),
                    html.Button(
                        Ico("close"),
                        id="btn-close-settings",
                        className="modal-close",
                        title="بستن",
                        **({"disabled": True, "style": {"opacity": "0.3", "cursor": "not-allowed"}}
                           if not is_configured() else {}),
                    ),
                ]),

                html.Div(className="settings-section settings-section-first", children=[
                    html.H3("اتصال SQL Server", className="settings-section-title"),
                    html.P(
                        "رمز عبور در Windows Credential Manager ذخیره می‌شود.",
                        className="settings-hint",
                    ),
                    html.Div(className="form-group", children=[
                        html.Label("Server / IP"),
                        dcc.Input(id="setup-server", className="form-input", type="text",
                                  placeholder="192.168.1.10 یا SERVER\\INSTANCE", value=cfg["server"]),
                    ]),
                    html.Div(className="form-group", children=[
                        html.Label("Database"),
                        dcc.Input(id="setup-database", className="form-input", type="text",
                                  placeholder="msdb", value=cfg["database"]),
                    ]),
                    html.Div(className="form-group", children=[
                        html.Label("Username"),
                        dcc.Input(id="setup-user", className="form-input", type="text",
                                  placeholder="sql_login", value=cfg["user"]),
                    ]),
                    html.Div(className="form-group", children=[
                        html.Label("Password"),
                        dcc.Input(
                            id="setup-password", className="form-input", type="password",
                            placeholder="رمز جدید (فقط برای تغییر)" if is_configured() else "رمز SQL Server",
                            value="",
                            autoComplete="new-password",
                        ),
                        html.P(
                            "رمز در Windows Credential Manager ذخیره شده — برای حفظ رمز فعلی این فیلد را "
                            "خالی بگذارید."
                            if is_configured() else
                            "در اولین ذخیره، رمز اینجا وارد و در Credential Manager ذخیره می‌شود.",
                            className="settings-hint",
                        ),
                    ]),
                    html.Div(className="form-group", children=[
                        html.Label("ODBC Driver"),
                        _native_select(
                            "setup-driver",
                            list_sql_driver_options(),
                            cfg["driver"] or "17",
                        ),
                    ]),
                ]),

                html.Div(className="permissions-box", children=[
                    html.H3([Ico("shield"), " دسترسی‌های مورد نیاز"]),
                    html.Ul([
                        html.Li("SELECT روی msdb.dbo.sysjobs"),
                        html.Li("SELECT روی msdb.dbo.sysjobsteps"),
                        html.Li("SELECT روی msdb.dbo.sysjobhistory"),
                        html.Li("SELECT روی msdb.dbo.sysjobactivity"),
                    ]),
                ]),

                html.Div(className="settings-section settings-section-last", children=[
                    html.H3("بروزرسانی خودکار", className="settings-section-title"),
                    html.Div(className="form-group", children=[
                        html.Label("فاصله بروزرسانی داده جاب‌ها"),
                        dcc.Dropdown(
                            id="setup-refresh-interval",
                            options=REFRESH_OPTIONS,
                            value=str(cfg.get("refresh_minutes", 5)),
                            clearable=False,
                            className="settings-dropdown",
                        ),
                        html.P(
                            "هر چند دقیقه یک‌بار داده جاب‌ها از SQL Server خوانده شود.",
                            className="settings-hint",
                        ),
                    ]),
                ]),

                html.Div(id="setup-message", className="setup-message"),
                html.Div(className="modal-actions", children=[
                    html.Button("تست اتصال", id="btn-test-connection", className="btn-primary", n_clicks=0),
                    html.Button("ذخیره بروزرسانی", id="btn-save-refresh", className="btn-primary", n_clicks=0),
                    html.Button("ذخیره اتصال", id="btn-save-connection", className="btn-success", n_clicks=0),
                ]),
            ]),
        ],
    )


def _detail_modal():
    return html.Div(
        id="detail-modal",
        className="modal-overlay hidden",
        children=[
            html.Div(className="modal-content modal-detail", children=[
                html.Div(className="modal-header", children=[
                    html.H2(id="detail-modal-title", children="جزئیات جاب"),
                    html.Button(Ico("close"), id="btn-close-detail",
                                className="modal-close", n_clicks=0, title="بستن"),
                ]),
                html.Div(id="detail-modal-body", className="detail-modal-body"),
            ]),
        ],
    )



app.layout = html.Div([
    dcc.Store(id="store-running"),
    dcc.Store(id="store-latest-runs"),
    dcc.Store(id="store-all-jobs"),
    dcc.Store(id="store-job-stats"),
    dcc.Store(id="store-today-runs"),
    dcc.Store(id="store-failures"),
    dcc.Store(id="store-latest-failures"),
    dcc.Store(id="store-overview"),
    dcc.Store(id="store-gantt"),
    dcc.Store(id="store-error"),
    dcc.Store(id="store-view", data="list"),
    dcc.Store(id="store-filter", data="all"),
    dcc.Store(id="store-search", data=""),
    dcc.Store(id="store-page", data=1),
    dcc.Store(id="store-gantt-filter", data="all"),
    dcc.Store(id="store-gantt-zoom", data=100),
    dcc.Store(id="store-paused", data=False),
    dcc.Store(id="store-snapshot-at", data=None),
    dcc.Store(id="store-data-loaded", data=False),
    dcc.Store(id="store-refresh-minutes", data=REFRESH_MINUTES),
    dcc.Interval(
        id="interval-refresh",
        interval=REFRESH_MINUTES * 60 * 1000,
        n_intervals=0,
    ),

    html.Div(
        id="app-splash",
        className="app-splash" if is_configured() else "app-splash hidden",
        children=[
            html.Div(className="app-splash-card", children=[
                html.Div(className="app-splash-spinner"),
                html.H2("Data Agent Monitor"),
                html.P("در حال آماده‌سازی برنامه...", className="app-splash-title"),
                html.P("در حال بارگذاری داده از SQL Server", className="app-splash-sub"),
            ]),
        ],
    ),

    html.Div(className="app-container", children=[
        html.Header(className="app-header animate-in", children=[
            html.Div(className="header-right", children=[
                html.Div(Ico("db", "logo-ico"), className="logo-icon"),
                html.Div(className="header-title", children=[
                    html.H1("Data Agent Monitor"),
                    html.Span("SQL Server Jobs Dashboard"),
                ]),
            ]),
            html.Div(className="header-left", children=[
                html.Div(id="live-indicator", className="live-indicator", children=[
                    html.Div(className="live-dot"),
                    "زنده",
                ]),
                html.Button(
                    [Ico("snapshot"), " Snapshot"],
                    id="btn-snapshot", className="header-btn refresh-btn", n_clicks=0,
                    title="ثبت لحظه‌ای — بدون بروزرسانی",
                ),
                html.Button(
                    [Ico("pause"), " توقف"],
                    id="btn-pause", className="header-btn refresh-btn", n_clicks=0,
                    title="توقف / ادامه بروزرسانی",
                ),
                html.Div(className="notif-wrap", children=[
                    html.Button(
                        [Ico("bell"), html.Span(id="notif-badge", className="notif-badge")],
                        id="btn-notifications", className="header-btn notif-btn", n_clicks=0,
                        title="اعلان‌های خطا",
                    ),
                ]),
                html.Button(
                    Ico("cog"), id="btn-open-settings", n_clicks=0,
                    className="header-btn", title="تنظیمات",
                ),
                html.Button(
                    [Ico("refresh"), " بروزرسانی"],
                    id="btn-refresh", className="header-btn refresh-btn", n_clicks=0,
                ),
            ]),
        ]),

        html.Nav(className="main-tabs", role="tablist", children=[
            html.Button(
                [Ico("list"), " جلسه جاری ",
                 html.Span(id="main-tab-badge", className="tab-badge")],
                id={"type": "main-tab", "view": "list"},
                className="main-tab active", n_clicks=0,
            ),
            html.Button(
                [Ico("gantt"), " Gantt"],
                id={"type": "main-tab", "view": "gantt"},
                className="main-tab", n_clicks=0,
            ),
        ]),

        html.Div(id="error-banner"),
        html.Div(
            id="refresh-status-bar",
            className="refresh-status-bar visible" if is_configured() else "refresh-status-bar hidden",
            children=[
                html.Span(className="refresh-spinner"),
                html.Span(id="refresh-status-text", children="در حال بارگذاری داده‌ها..."),
            ],
        ),
        html.Div(id="freeze-banner", className="freeze-banner hidden"),

        html.Div(id="list-panel", className="view-panel active", children=[
            dcc.Loading(
                id="loading-main",
                type="circle",
                color="#3dd9b6",
                parent_style={"minHeight": "320px"},
                children=html.Div(className="list-panel-inner", children=[
                    html.Section(id="stats-grid", className="stats-grid", **{"aria-label": "خلاصه وضعیت"}),
                    html.Div(className="toolbar animate-in", children=[
                        html.Div(id="filter-tabs", className="toolbar-right", role="tablist"),
                        html.Div(className="toolbar-left", children=[
                            html.Div(className="search-box", children=[
                                Ico("search", "search-ico"),
                                dcc.Input(id="search-input", className="search-input", type="text",
                                          placeholder="جستجوی نام جاب...", debounce=True),
                            ]),
                        ]),
                    ]),
                    html.Main(className="jobs-container animate-in", **{"aria-label": "لیست جاب‌ها"}, children=[
                        html.Div(className="jobs-header", role="row", children=[
                            html.Div("نام جاب", role="columnheader"),
                            html.Div("وضعیت", role="columnheader"),
                            html.Div("پیشرفت", role="columnheader"),
                            html.Div("مدت اجرا", role="columnheader"),
                            html.Div("اجرای بعدی", role="columnheader"),
                            html.Div(role="columnheader"),
                        ]),
                        html.Div(id="jobs-body", role="rowgroup", children=[
                            html.Div(className="loading-state", children="در حال بارگذاری داده‌ها..."),
                        ]),
                        html.Div(id="pagination-bar", className="pagination-bar"),
                    ]),
                ]),
            ),
        ]),

        html.Div(id="gantt-panel", className="view-panel", children=[
            html.Div(className="gantt-wrapper", children=[
                html.Div(className="gantt-toolbar", children=[
                    html.Div(className="gantt-toolbar-right", children=[
                        html.Button("همه", id={"type": "gantt-filter", "filter": "all"},
                                    className="gantt-filter-chip active", n_clicks=0),
                        html.Button([html.Span(className="chip-dot running"), " اجرا"],
                                    id={"type": "gantt-filter", "filter": "running"},
                                    className="gantt-filter-chip", n_clicks=0),
                        html.Button([html.Span(className="chip-dot error"), " خطا"],
                                    id={"type": "gantt-filter", "filter": "error"},
                                    className="gantt-filter-chip", n_clicks=0),
                        html.Button([html.Span(className="chip-dot success"), " موفق"],
                                    id={"type": "gantt-filter", "filter": "success"},
                                    className="gantt-filter-chip", n_clicks=0),
                        html.Button([html.Span(className="chip-dot failed"), " شکست"],
                                    id={"type": "gantt-filter", "filter": "failed"},
                                    className="gantt-filter-chip", n_clicks=0),
                    ]),
                    html.Div(className="gantt-toolbar-left", children=[
                        html.Span(className="gantt-day-label", id="gantt-day-label"),
                        html.Button(Ico("zoom-out"), id="btn-gantt-zoom-out",
                                    className="gantt-zoom-btn", n_clicks=0, title="کوچک‌نمایی"),
                        html.Span("100%", id="gantt-zoom-label", className="gantt-zoom-label"),
                        html.Button(Ico("zoom-in"), id="btn-gantt-zoom-in",
                                    className="gantt-zoom-btn", n_clicks=0, title="بزرگ‌نمایی"),
                    ]),
                ]),
                html.Div(id="gantt-chart-area"),
            ]),
        ]),

    ]),

    _settings_modal(open_by_default=not is_configured()),
    _detail_modal(),
    html.Div(
        id="notif-modal",
        className="modal-overlay hidden",
        children=[
            html.Div(className="modal-content notif-modal-content", children=[
                html.Div(className="modal-header", children=[
                    html.H2([Ico("bell"), " خطاهای امروز"]),
                    html.Button(Ico("close"), id="btn-close-notif",
                                className="modal-close", n_clicks=0, title="بستن"),
                ]),
                html.Div(id="notif-panel-body", className="notif-modal-body"),
            ]),
        ],
    ),
])


# ── Data fetch ────────────────────────────────────────────────────────────────
@app.callback(
    Output("store-running", "data"),
    Output("store-latest-runs", "data"),
    Output("store-all-jobs", "data"),
    Output("store-job-stats", "data"),
    Output("store-today-runs", "data"),
    Output("store-failures", "data"),
    Output("store-latest-failures", "data"),
    Output("store-error", "data"),
    Output("store-data-loaded", "data"),
    Output("refresh-status-bar", "className"),
    Input("interval-refresh", "n_intervals"),
    Input("btn-refresh", "n_clicks"),
    State("store-paused", "data"),
    prevent_initial_call=False,
)
def fetch_all_data(_, __, paused):
    hidden = "refresh-status-bar hidden"
    if paused:
        return (dash.no_update,) * 8 + (hidden,)
    if not is_configured():
        return (dash.no_update,) * 7 + (None, False, hidden)
    if ctx.triggered_id == "btn-refresh":
        invalidate_batch_cache()
    try:
        running = get_running_jobs()
        latest, all_jobs, job_stats, today, today_fail, latest_fail = get_dashboard_batch(
            use_cache=(ctx.triggered_id != "btn-refresh"),
        )
        return (
            _serialize_rows(running),
            _serialize_rows(latest),
            _serialize_rows(all_jobs),
            job_stats,
            _serialize_rows(today),
            _serialize_rows(today_fail),
            _serialize_rows(latest_fail),
            None,
            True,
            hidden,
        )
    except Exception as e:
        return (
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            dash.no_update,
            str(e),
            False,
            hidden,
        )


@app.callback(
    Output("app-splash", "className"),
    Input("store-data-loaded", "data"),
    Input("store-error", "data"),
)
def toggle_app_splash(data_loaded, error):
    if not is_configured():
        return "app-splash hidden"
    if data_loaded or error:
        return "app-splash hidden"
    return "app-splash"


@app.callback(
    Output("refresh-status-bar", "className", allow_duplicate=True),
    Output("refresh-status-text", "children", allow_duplicate=True),
    Input("btn-refresh", "n_clicks"),
    Input("interval-refresh", "n_intervals"),
    prevent_initial_call=True,
)
def show_refresh_bar(_, __):
    return "refresh-status-bar visible", "⟳ در حال بروزرسانی داده‌ها..."


@app.callback(
    Output("setup-refresh-interval", "value"),
    Input("btn-open-settings", "n_clicks"),
    prevent_initial_call=True,
)
def load_saved_refresh_interval(_):
    return str(load_config().get("refresh_minutes", 5))


@app.callback(
    Output("interval-refresh", "interval"),
    Output("store-refresh-minutes", "data"),
    Output("setup-message", "children", allow_duplicate=True),
    Output("setup-message", "className", allow_duplicate=True),
    Input("btn-save-refresh", "n_clicks"),
    State("setup-refresh-interval", "value"),
    prevent_initial_call=True,
)
def update_refresh_interval(save_refresh_clicks, minutes):
    if not save_refresh_clicks:
        return (dash.no_update,) * 4
    parsed = _parse_refresh_minutes(minutes)
    if parsed not in _VALID_REFRESH:
        return dash.no_update, dash.no_update, "فاصله بروزرسانی نامعتبر است.", "setup-message err"
    save_refresh_minutes(parsed)
    msg = f"✓ بروزرسانی خودکار: هر {parsed} دقیقه (ذخیره شد — بعد از ری‌استارت هم باقی می‌ماند)"
    return parsed * 60 * 1000, parsed, msg, "setup-message ok"


# ── Pause / Snapshot ──────────────────────────────────────────────────────────
@app.callback(
    Output("store-paused", "data"),
    Output("store-snapshot-at", "data"),
    Output("btn-pause", "children", allow_duplicate=True),
    Output("btn-pause", "className", allow_duplicate=True),
    Input("btn-snapshot", "n_clicks"),
    prevent_initial_call=True,
)
def take_snapshot(_):
    return (
        True,
        datetime.now().strftime("%H:%M:%S"),
        [Ico("play"), " ادامه"],
        "header-btn refresh-btn pause-active",
    )


@app.callback(
    Output("store-paused", "data", allow_duplicate=True),
    Output("store-snapshot-at", "data", allow_duplicate=True),
    Output("btn-pause", "children"),
    Output("btn-pause", "className"),
    Input("btn-pause", "n_clicks"),
    State("store-paused", "data"),
    prevent_initial_call=True,
)
def toggle_pause(_, paused):
    if paused:
        return False, None, [Ico("pause"), " توقف"], "header-btn refresh-btn"
    return True, None, [Ico("play"), " ادامه"], "header-btn refresh-btn pause-active"


@app.callback(
    Output("interval-refresh", "disabled"),
    Input("store-paused", "data"),
)
def disable_intervals(paused):
    return bool(paused)


@app.callback(
    Output("freeze-banner", "children"),
    Output("freeze-banner", "className"),
    Output("live-indicator", "children"),
    Output("live-indicator", "className"),
    Input("store-paused", "data"),
    Input("store-snapshot-at", "data"),
)
def update_freeze_ui(paused, snapshot_at):
    if not paused:
        return (
            None, "freeze-banner hidden",
            [html.Div(className="live-dot"), "زنده"],
            "live-indicator",
        )
    if snapshot_at:
        return (
            f"📷 Snapshot — {snapshot_at}  ·  "
            f"داده‌ها در این لحظه ثابت است. برای بروزرسانی «ادامه» را بزنید.",
            "freeze-banner snapshot-mode",
            [html.Span("📷", className="ico"), " Snapshot"],
            "live-indicator snapshot-mode",
        )
    return (
        "⏸ بروزرسانی خودکار متوقف است — «ادامه» را بزنید.",
        "freeze-banner pause-mode",
        [html.Span("⏸", className="ico"), " متوقف"],
        "live-indicator pause-mode",
    )


@app.callback(
    Output("store-overview", "data"),
    Input("store-running", "data"),
    Input("store-latest-runs", "data"),
    Input("store-all-jobs", "data"),
    Input("store-latest-failures", "data"),
    Input("store-job-stats", "data"),
)
def merge_overview(running_data, latest_data, all_jobs_data, latest_failures, job_stats_data):
    if not all_jobs_data:
        return []
    running = []
    for r in running_data or []:
        row = dict(r)
        row["start_dt"] = _parse_dt(r.get("start_dt"))
        running.append(row)
    latest = []
    for h in latest_data or []:
        row = dict(h)
        if row.get("duration_seconds") is None:
            row["duration_seconds"] = parse_run_duration(row.get("run_duration") or 0)
        latest.append(row)
    all_jobs = [dict(j) for j in all_jobs_data]
    failure_map = {f["job_id"]: f for f in (latest_failures or [])}
    job_stats = job_stats_data or {}
    return build_jobs_overview(all_jobs, running, latest, job_stats, failure_map)


@app.callback(
    Output("store-gantt", "data"),
    Input("store-running", "data"),
    Input("store-today-runs", "data"),
    Input("store-job-stats", "data"),
    Input("store-view", "data"),
)
def merge_gantt(running_data, today_data, job_stats_data, view):
    if view != "gantt":
        return dash.no_update
    if today_data is None:
        return []
    running = []
    for r in running_data or []:
        row = dict(r)
        row["start_dt"] = _parse_dt(r.get("start_dt"))
        running.append(row)
    today = [_enrich_run_row(h) for h in (today_data or [])]
    job_stats = job_stats_data or {}
    return build_gantt_rows(today, running, job_stats)


# ── Error banner ──────────────────────────────────────────────────────────────
@app.callback(Output("error-banner", "children"), Input("store-error", "data"))
def show_error(err):
    if not err:
        return None
    return html.Div([
        html.I(className="fas fa-exclamation-triangle", style={"marginLeft": "8px"}),
        " خطا در اتصال: ", html.Strong(str(err)),
    ], className="error-banner")


# ── Stats + filter tabs + notification badge ──────────────────────────────────
def _count_by_status(jobs):
    counts = {"running": 0, "error": 0, "success": 0, "failed": 0, "idle": 0}
    for j in jobs:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    return counts


@app.callback(
    Output("stats-grid", "children"),
    Output("filter-tabs", "children"),
    Input("store-overview", "data"),
)
def render_stats_and_filters(jobs):
    jobs = jobs or []
    counts = _count_by_status(jobs)
    total = len(jobs)
    enabled = sum(1 for j in jobs if j.get("steps") != "غیرفعال")

    stat_defs = [
        ("running", "در حال اجرا", counts["running"], f"از {enabled} جاب فعال", "play"),
        ("error", "خطا", counts["error"], "نیاز به بررسی", "warn"),
        ("success", "موفق", counts["success"], "آخرین اجرا", "ok"),
        ("failed", "شکست‌خورده", counts["failed"], "بازتلاش خودکار", "fail"),
        ("idle", "غیرفعال", counts["idle"], "غیرفعال شده", "pause"),
    ]
    stats = []
    for i, (key, label, val, sub, icon) in enumerate(stat_defs):
        stats.append(html.Div(
            id={"type": "stat-card", "filter": key},
            className=f"stat-card {key} animate-in",
            style={"animationDelay": f"{0.05 + i * 0.05}s"},
            n_clicks=0,
            children=[
                html.Div(className="stat-header", children=[
                    html.Span(label, className="stat-label"),
                    html.Div(Ico(icon), className="stat-icon"),
                ]),
                html.Div(str(val), className="stat-value"),
                html.Div(sub, className="stat-sub"),
            ],
        ))

    tab_defs = [
        ("all", "همه جاب‌ها", None, None),
        ("running", "اجرا", counts["running"], "running-count"),
        ("error", "خطا", counts["error"], "error-count"),
        ("success", "موفق", counts["success"], "success-count"),
        ("failed", "شکست", counts["failed"], "failed-count"),
    ]
    tabs = []
    for key, label, cnt, cnt_cls in tab_defs:
        children = [label]
        if cnt is not None:
            children = [html.Span(str(cnt), className=f"count {cnt_cls}"), f" {label}"]
        tabs.append(html.Button(
            id={"type": "filter-tab", "filter": key},
            className="filter-tab",
            n_clicks=0,
            children=children,
        ))

    return stats, tabs


@app.callback(
    Output("notif-modal", "className"),
    Input("btn-notifications", "n_clicks"),
    Input("btn-close-notif", "n_clicks"),
    State("notif-modal", "className"),
    prevent_initial_call=True,
)
def toggle_notif_modal(open_clicks, close_clicks, current):
    triggered = ctx.triggered_id
    if triggered == "btn-close-notif":
        return "modal-overlay hidden"
    if triggered == "btn-notifications":
        if current and "hidden" not in current:
            return "modal-overlay hidden"
        return "modal-overlay"
    return dash.no_update


@app.callback(
    Output("notif-panel-body", "children"),
    Input("store-failures", "data"),
)
def render_notif_panel(failures):
    if not failures:
        return html.Div("✓ خطایی امروز ثبت نشده.", className="notif-empty")
    items = []
    for f in failures:
        dt = parse_run_datetime(f.get("run_date"), f.get("run_time"))
        time_str = dt.strftime("%H:%M:%S") if dt else "—"
        date_str = dt.strftime("%Y/%m/%d") if dt else ""
        step = f.get("step_name") or f"Step {f.get('step_id', '?')}"
        msg = (f.get("message") or "بدون پیام").strip()
        items.append(html.Div(className="notif-item", children=[
            html.Div(className="notif-item-top", children=[
                html.Strong(f.get("name", "?"), className="notif-job"),
                html.Span(f"{date_str} {time_str}".strip(), className="notif-time"),
            ]),
            html.Div(step, className="notif-step"),
            html.Div(msg[:300], className="notif-msg", title=msg),
        ]))
    return items


@app.callback(
    Output("notif-badge", "children"),
    Output("notif-badge", "style"),
    Input("store-failures", "data"),
)
def update_notif_badge(failures):
    n = len(failures or [])
    style = {"display": "flex"} if n > 0 else {"display": "none"}
    return str(n) if n else "", style


@app.callback(Output("main-tab-badge", "children"), Input("store-overview", "data"))
def update_main_tab_badge(jobs):
    return str(len(jobs or []))


# ── Main view tabs ────────────────────────────────────────────────────────────
@app.callback(
    Output("list-panel", "className"),
    Output("gantt-panel", "className"),
    Output({"type": "main-tab", "view": ALL}, "className"),
    Output("store-view", "data"),
    Input({"type": "main-tab", "view": ALL}, "n_clicks"),
    State({"type": "main-tab", "view": ALL}, "id"),
    prevent_initial_call=True,
)
def switch_main_view(_, tab_ids):
    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    view = triggered["view"]
    list_cls = "view-panel active" if view == "list" else "view-panel"
    gantt_cls = "view-panel active" if view == "gantt" else "view-panel"
    tab_classes = [
        "main-tab active" if t["view"] == view else "main-tab" for t in tab_ids
    ]
    return list_cls, gantt_cls, tab_classes, view


# ── Filter / search / page state ──────────────────────────────────────────────
@app.callback(
    Output("store-filter", "data"),
    Output("store-page", "data", allow_duplicate=True),
    Input({"type": "filter-tab", "filter": ALL}, "n_clicks"),
    Input({"type": "stat-card", "filter": ALL}, "n_clicks"),
    State({"type": "filter-tab", "filter": ALL}, "id"),
    State({"type": "stat-card", "filter": ALL}, "id"),
    prevent_initial_call=True,
)
def set_filter(tab_clicks, stat_clicks, tab_ids, stat_ids):
    triggered = ctx.triggered_id
    if not triggered or not isinstance(triggered, dict):
        return dash.no_update, dash.no_update
    f = triggered.get("filter")
    if f:
        return f, 1
    return dash.no_update, dash.no_update


@app.callback(Output("store-search", "data"), Input("search-input", "value"))
def set_search(value):
    return (value or "").strip()


@app.callback(
    Output("store-page", "data", allow_duplicate=True),
    Input("store-search", "data"),
    prevent_initial_call=True,
)
def reset_page_on_search(_):
    return 1


@app.callback(
    Output({"type": "filter-tab", "filter": ALL}, "className"),
    Input("store-filter", "data"),
    State({"type": "filter-tab", "filter": ALL}, "id"),
)
def highlight_filter_tab(active, ids):
    return [
        "filter-tab active" if i["filter"] == active else "filter-tab"
        for i in ids
    ]


# ── Jobs list + pagination ──────────────────────────────────────────────────────
def _status_badge(status):
    pulse = html.Span(className="pulse-dot") if status == "running" else None
    children = [c for c in [pulse, STATUS_UI.get(status, status)] if c is not None]
    return html.Span(children, className=f"status-badge {status}")


@app.callback(
    Output("jobs-body", "children"),
    Output("pagination-bar", "children"),
    Input("store-overview", "data"),
    Input("store-filter", "data"),
    Input("store-search", "data"),
    Input("store-page", "data"),
    Input("store-data-loaded", "data"),
    Input("store-all-jobs", "data"),
)
def render_jobs(jobs, filt, search, page, data_loaded, all_jobs_data):
    if is_configured() and not data_loaded and all_jobs_data is None:
        return (
            html.Div(className="loading-state", children="در حال بارگذاری داده‌ها..."),
            [],
        )

    jobs = jobs or []
    page = page or 1

    filtered = jobs
    if filt and filt != "all":
        filtered = [j for j in filtered if j["status"] == filt]
    if search:
        s = search.lower()
        filtered = [j for j in filtered if s in j["name"].lower()]

    total = len(filtered)
    if total == 0:
        if not jobs and data_loaded:
            msg = "هیچ جابی یافت نشد"
        else:
            msg = "جابی با این فیلتر یافت نشد"
        empty = html.Div(className="empty-state", children=[
            html.I(className="fas fa-search"),
            html.Div(msg),
        ])
        return empty, _pagination_bar(0, 1, 1)

    total_pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    page_jobs = filtered[start:start + PAGE_SIZE]

    rows = []
    for job in page_jobs:
        pct = min(100, max(0, int(job.get("progress") or 0)))
        name_cell_children = [
            html.Div(job["name"], className="job-name", title=job["name"]),
            html.Div([
                Ico("db", "tiny-ico"),
                f" {job['category']}",
            ], className="job-category"),
        ]
        if job.get("status") == "error" and (job.get("failedStep") or job.get("errorMessage")):
            err_parts = []
            if job.get("failedStep"):
                err_parts.append(html.Span(f"SP/Step: {job['failedStep']}", className="err-step"))
            if job.get("errorMessage"):
                err_parts.append(html.Span(job["errorMessage"][:120], className="err-msg",
                                           title=job.get("errorMessage", "")))
            name_cell_children.append(html.Div(err_parts, className="job-error-line"))

        rows.append(html.Div(className="job-row", role="row", children=[
            html.Div(className="job-name-cell", role="gridcell", children=name_cell_children),
            html.Div(_status_badge(job["status"]), role="gridcell"),
            html.Div(className="progress-cell", role="gridcell", children=[
                html.Div(html.Div(className=f"progress-bar-fill {job['status']}",
                                  style={"width": f"{pct}%"}),
                         className="progress-bar-wrapper"),
                html.Span(f"{pct}%", className="progress-text"),
            ]),
            html.Div([
                Ico("clock", "tiny-ico"),
                f" {job['duration']}",
            ], className="time-cell", role="gridcell"),
            html.Div(job.get("nextRun", "—"), className="next-run-cell", role="gridcell"),
            html.Div(role="gridcell", children=[
                html.Button(
                    Ico("dots"),
                    id={"type": "job-detail-btn", "job_id": job["job_id"]},
                    className="action-btn", n_clicks=0, title="جزئیات خطا",
                ),
            ]),
        ]))

    return rows, _pagination_bar(total, page, total_pages)


def _pagination_bar(total, page, total_pages):
    start_n = (page - 1) * PAGE_SIZE + 1 if total else 0
    end_n = min(page * PAGE_SIZE, total)
    return [
        html.Div(
            ["نمایش ", html.Strong(str(start_n)), " تا ", html.Strong(str(end_n)),
             " از ", html.Strong(str(total)), " جاب"],
            className="pagination-info",
        ),
        html.Div(className="pagination-controls", children=[
            html.Button(Ico("chev-r"), id="btn-page-prev",
                        className="page-btn", n_clicks=0, disabled=(page <= 1),
                        title="صفحه قبل"),
            html.Span(f"{page} / {total_pages}", className="page-btn",
                      style={"border": "none", "cursor": "default"}),
            html.Button(Ico("chev-l"), id="btn-page-next",
                        className="page-btn", n_clicks=0, disabled=(page >= total_pages),
                        title="صفحه بعد"),
        ]),
    ]


@app.callback(
    Output("store-page", "data"),
    Input("btn-page-prev", "n_clicks"),
    Input("btn-page-next", "n_clicks"),
    State("store-page", "data"),
    prevent_initial_call=True,
)
def paginate(prev, nxt, page):
    triggered = ctx.triggered_id
    page = page or 1
    if triggered == "btn-page-prev":
        return max(1, page - 1)
    if triggered == "btn-page-next":
        return page + 1
    return dash.no_update


# ── Gantt ─────────────────────────────────────────────────────────────────────
@app.callback(
    Output("store-gantt-filter", "data"),
    Input({"type": "gantt-filter", "filter": ALL}, "n_clicks"),
    State({"type": "gantt-filter", "filter": ALL}, "id"),
    prevent_initial_call=True,
)
def set_gantt_filter(_, ids):
    triggered = ctx.triggered_id
    if triggered and isinstance(triggered, dict):
        return triggered["filter"]
    return dash.no_update


@app.callback(
    Output({"type": "gantt-filter", "filter": ALL}, "className"),
    Input("store-gantt-filter", "data"),
    State({"type": "gantt-filter", "filter": ALL}, "id"),
)
def highlight_gantt_filter(active, ids):
    return [
        "gantt-filter-chip active" if i["filter"] == active else "gantt-filter-chip"
        for i in ids
    ]


@app.callback(
    Output("store-gantt-zoom", "data"),
    Output("gantt-zoom-label", "children"),
    Input("btn-gantt-zoom-in", "n_clicks"),
    Input("btn-gantt-zoom-out", "n_clicks"),
    State("store-gantt-zoom", "data"),
    prevent_initial_call=True,
)
def gantt_zoom(zin, zout, zoom):
    triggered = ctx.triggered_id
    zoom = zoom or 100
    if triggered == "btn-gantt-zoom-in":
        zoom = min(200, zoom + 20)
    elif triggered == "btn-gantt-zoom-out":
        zoom = max(40, zoom - 20)
    return zoom, f"{zoom}%"


@app.callback(
    Output("gantt-chart-area", "children"),
    Output("gantt-day-label", "children"),
    Input("store-gantt", "data"),
    Input("store-gantt-filter", "data"),
    Input("store-gantt-zoom", "data"),
    Input("store-view", "data"),
)
def render_gantt_chart(gantt_rows, gantt_filter, zoom, view):
    if view != "gantt":
        return dash.no_update, dash.no_update
    gantt_rows = gantt_rows or []
    zoom = max(40, min(200, zoom or 100))
    cell_w = GANTT_BASE_CELL * (zoom / 100)
    total_w = GANTT_HOURS * cell_w
    today_str = datetime.now().strftime("%Y-%m-%d")

    if gantt_filter and gantt_filter != "all":
        gantt_rows = [
            r for r in gantt_rows
            if any(b["status"] == gantt_filter for b in r.get("bars", []))
        ]

    if not gantt_rows:
        empty = html.Div(className="empty-state", style={"padding": "48px"}, children=[
            Ico("gantt"),
            html.Div("امروز اجرایی برای نمایش وجود ندارد"),
        ])
        return empty, f"امروز: {today_str}"

    time_cells = [
        html.Div(f"{h:02d}:00", className="gantt-time-cell", style={"width": f"{cell_w}px"})
        for h in range(GANTT_HOURS)
    ]
    grid_lines = [
        html.Div(className="gantt-grid-line", style={"left": f"{h * cell_w}px"})
        for h in range(GANTT_HOURS + 1)
    ]

    now = datetime.now()
    now_min = now.hour * 60 + now.minute + now.second / 60
    now_left = (now_min / GANTT_DAY_MINUTES) * total_w

    label_rows = [html.Div("نام جاب", className="gantt-label-header")]
    gantt_row_els = []

    for row in gantt_rows:
        label_rows.append(html.Div(className="gantt-label-row", children=[
            html.Span(className=f"gantt-label-status-dot {row['row_status']}"),
            html.Span(row["name"], className="gantt-label-name", title=row["name"]),
        ]))

        bars = []
        for bar in row.get("bars", []):
            left = (bar["start_min"] / GANTT_DAY_MINUTES) * total_w
            width = max(
                ((bar["end_min"] - bar["start_min"]) / GANTT_DAY_MINUTES) * total_w, 6
            )
            tip = (
                f"{row['name']}\n"
                f"{bar['start_str']} → {bar['end_str']}\n"
                f"{STATUS_UI.get(bar['status'], bar['status'])} — {bar['duration_str']}"
            )
            bars.append(html.Div(
                className=f"gantt-bar {bar['status']}",
                style={"left": f"{left}px", "width": f"{width}px"},
                title=tip,
                children=[
                    html.Div(className="gantt-bar-progress",
                             style={"width": f"{bar['progress']}%"}),
                ],
            ))
        gantt_row_els.append(html.Div(className="gantt-row", children=bars))

    chart = html.Div(className="gantt-chart", children=[
        html.Div(className="gantt-area", children=[
            html.Div(
                id="gantt-timeline-scroll",
                className="gantt-timeline-wrapper",
                title="Drag برای جابجایی timeline",
                children=[
                    html.Div(className="gantt-timeline", style={"width": f"{total_w}px"}, children=[
                        html.Div(className="gantt-time-header", children=time_cells),
                        html.Div(className="gantt-grid", children=grid_lines),
                        html.Div(className="gantt-rows", children=gantt_row_els),
                        html.Div(
                            id="gantt-now-line",
                            className="gantt-now-line",
                            style={"left": f"{now_left}px"},
                        ),
                    ]),
                ],
            ),
            html.Div(id="gantt-labels", className="gantt-labels", children=label_rows),
        ]),
    ])
    return chart, f"امروز: {today_str}"


# ── Settings modal ──────────────────────────────────────────────────────────────
@app.callback(
    Output("settings-modal", "className"),
    Input("btn-open-settings", "n_clicks"),
    Input("btn-close-settings", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_settings(open_clicks, close_clicks):
    triggered = ctx.triggered_id
    if triggered == "btn-open-settings":
        return "modal-overlay"
    if triggered == "btn-close-settings" and is_configured():
        return "modal-overlay hidden"
    return dash.no_update


def _is_local_request() -> bool:
    addr = request.remote_addr
    return addr in (None, "127.0.0.1", "::1")


@app.callback(
    Output("setup-message", "children", allow_duplicate=True),
    Output("setup-message", "className", allow_duplicate=True),
    Output("settings-modal", "className", allow_duplicate=True),
    Output("btn-close-settings", "disabled"),
    Output("btn-close-settings", "style"),
    Input("btn-test-connection", "n_clicks"),
    Input("btn-save-connection", "n_clicks"),
    State("setup-server", "value"),
    State("setup-database", "value"),
    State("setup-user", "value"),
    State("setup-password", "value"),
    State("setup-driver", "value"),
    prevent_initial_call=True,
)
def setup_feedback(test_clicks, save_clicks, server, database, user, password, driver):
    triggered = ctx.triggered_id
    if not _is_local_request():
        return (
            "تنظیمات اتصال فقط از همین رایانه قابل تغییر است.",
            "setup-message err",
            dash.no_update,
            not is_configured(),
            {"opacity": "0.3", "cursor": "not-allowed"} if not is_configured() else {},
        )
    if not server or not user:
        return (
            "Server و Username الزامی هستند.",
            "setup-message err",
            dash.no_update,
            not is_configured(),
            {"opacity": "0.3", "cursor": "not-allowed"} if not is_configured() else {},
        )
    if not driver or str(driver).strip() == "":
        driver = load_config().get("driver") or "17"
    resolved = resolve_password(server, user, password)
    if not resolved:
        hint = (
            "Password الزامی است — یا فیلد را خالی بگذارید تا رمز ذخیره‌شده استفاده شود."
            if is_configured() else "Password الزامی است."
        )
        return (
            hint,
            "setup-message err",
            dash.no_update,
            not is_configured(),
            {"opacity": "0.3", "cursor": "not-allowed"} if not is_configured() else {},
        )
    try:
        ok, msg = test_connection(server, user, resolved, database, driver)
        if triggered == "btn-save-connection" and ok:
            save_config(server, user, resolved, database, driver)
            return (
                "اتصال ذخیره شد.",
                "setup-message ok",
                "modal-overlay hidden",
                False,
                {},
            )
        return (
            msg,
            "setup-message ok" if ok else "setup-message err",
            dash.no_update,
            not is_configured(),
            {"opacity": "0.3", "cursor": "not-allowed"} if not is_configured() else {},
        )
    except Exception as ex:
        return (
            f"اتصال برقرار نشد: {ex}",
            "setup-message err",
            dash.no_update,
            not is_configured(),
            {"opacity": "0.3", "cursor": "not-allowed"} if not is_configured() else {},
        )


# ── Detail modal ────────────────────────────────────────────────────────────────
@app.callback(
    Output("detail-modal", "className"),
    Output("detail-modal-title", "children"),
    Output("detail-modal-body", "children"),
    Input({"type": "job-detail-btn", "job_id": ALL}, "n_clicks"),
    Input("btn-close-detail", "n_clicks"),
    State("store-overview", "data"),
    prevent_initial_call=True,
)
def show_detail(detail_clicks, close_click, overview):
    triggered = ctx.triggered_id
    if triggered == "btn-close-detail":
        return "modal-overlay hidden", dash.no_update, dash.no_update
    if isinstance(triggered, dict) and triggered.get("type") == "job-detail-btn":
        if not any(c for c in detail_clicks if c):
            return dash.no_update, dash.no_update, dash.no_update
        job_id = triggered["job_id"]
        job_name = job_id
        job_info = {}
        for j in overview or []:
            if j["job_id"] == job_id:
                job_name = j["name"]
                job_info = j
                break
        try:
            definitions = get_job_step_definitions(job_id)
            grouped = get_step_runs_grouped(job_id, max_runs=20, since_days=None)
        except Exception as e:
            return "modal-overlay", job_name, html.Div(f"خطا: {e}", style={"color": "var(--accent-error)"})

        runs_list = _parse_grouped_runs(grouped)
        latest = runs_list[0] if runs_list else None
        older = runs_list[1:] if len(runs_list) > 1 else []

        body_parts = []

        body_parts.append(_build_job_summary_card(job_info, latest))

        if job_info.get("status") == "error":
            body_parts.append(html.Div(className="detail-error-box", children=[
                html.Div("⚠ جزئیات آخرین خطا", className="detail-error-title"),
                html.Div(f"Step/SP: {job_info.get('failedStep') or '—'}", className="detail-error-step"),
                html.Pre(job_info.get("errorMessage") or "—", className="detail-error-msg"),
            ]))

        latest_sec = _build_latest_run_section(latest)
        if latest_sec:
            body_parts.append(latest_sec)

        older_sec = _build_grouped_runs_section(older, empty_ok=True)
        if older_sec:
            body_parts.append(older_sec)
        elif not latest:
            body_parts.append(_build_grouped_runs_section([]))

        def_section = _build_job_definition_section(definitions, latest)
        if def_section:
            body_parts.append(def_section)

        if not definitions and not runs_list:
            body_parts.append(html.P(
                "تعریف step برای این جاب یافت نشد.",
                style={"color": "var(--text-muted)"},
            ))

        return "modal-overlay", job_name, html.Div(className="detail-modal-inner", children=body_parts)
    return dash.no_update, dash.no_update, dash.no_update


if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    if is_configured():
        print("Testing SQL Server connection...")
        try:
            from db import get_connection
            conn = get_connection()
            conn.close()
            print("Connected OK")
        except Exception as e:
            print(f"Connection failed: {e}")
    else:
        print("No .env — open http://localhost:%s and configure in Settings." % DASH_PORT)
    app.run(debug=False, host=DASH_HOST, port=DASH_PORT)
