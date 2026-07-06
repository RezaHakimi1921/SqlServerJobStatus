# SQL Server Agent Monitor

A lightweight web dashboard to monitor **SQL Server Agent Jobs** — running jobs, completed runs, Gantt timeline, and step-level details.

---

## Quick Start (Windows)

### Prerequisites

- Python 3.9+
- [ODBC Driver 17 or 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- A SQL login with **SELECT** on `msdb` (`sysjobs`, `sysjobhistory`, `sysjobactivity`)

### Install & Run

```bat
setup.bat    REM install dependencies (first time only)
run.bat      REM starts the app and opens the browser
```

On **first run**, a setup wizard asks for Server, User, and Password. The password is stored in **Windows Credential Manager** (not in `.env`). Server settings are in `.env` (never committed to git).

**Security:** The app binds to `127.0.0.1` by default (local access only). Connection settings can only be changed from the same machine. Gantt and all views use the same read-only SQL connection — credentials never reach the browser.

---

## Features

| Tab | Description |
|-----|-------------|
| ⚡ Running | Live jobs with progress estimate and slow-job detection |
| 📋 All Jobs | Latest run per job, filter by date |
| 📊 Gantt | Timeline of today's job executions |
| 🔍 Details | Step-level history for a selected job |

---

## Configuration

Settings are stored in `.env` (auto-created by the setup wizard):

| Variable | Default | Description |
|----------|---------|-------------|
| `SQL_SERVER` | — | Server name or `HOST\INSTANCE` |
| `SQL_DATABASE` | `msdb` | Database (keep as msdb) |
| `SQL_USER` | — | SQL login |
| *(password)* | — | Stored in Windows Credential Manager |
| `SQL_DRIVER` | `17` | ODBC driver version (17 or 18) |
| `DASH_HOST` | `127.0.0.1` | Bind address (local only by default) |
| `REFRESH_RUNNING` | `15000` | Running jobs refresh (ms) |
| `REFRESH_HISTORY` | `60000` | History refresh (ms) |
| `DASH_PORT` | `8050` | Web UI port |

Use **تغییر اتصال** (Change Connection) in the header to reconfigure.

---

## Tech Stack

- Python · Dash · Plotly · pyodbc

---

---

# مانیتور SQL Server Agent

داشبورد وب سبک برای مشاهده وضعیت **جاب‌های SQL Server Agent** — در حال اجرا، تمام‌شده، Gantt و جزئیات Step.

---

## شروع سریع (ویندوز)

### پیش‌نیاز

- Python 3.9+
- ODBC Driver 17 یا 18 for SQL Server
- یک SQL Login با دسترسی **SELECT** روی `msdb`

### نصب و اجرا

```bat
setup.bat    REM نصب پکیج‌ها (فقط بار اول)
run.bat      REM اجرا + باز کردن مرورگر
```

در **اولین اجرا**، فرم Setup از شما Server، User و Password می‌گیرد. **رمز عبور** در Windows Credential Manager ذخیره می‌شود (نه در `.env`).

**امنیت:** پیش‌فرض فقط از `127.0.0.1` در دسترس است. تنظیمات اتصال فقط از همان رایانه قابل تغییر است. Gantt و همه بخش‌ها از همان اتصال SQL استفاده می‌کنند — رمز هرگز به مرورگر ارسال نمی‌شود.

---

## امکانات

| تب | توضیح |
|----|-------|
| ⚡ در حال اجرا | جاب‌های live + تخمین پیشرفت |
| 📋 همه جاب‌ها | آخرین اجرای هر جاب + فیلتر تاریخ |
| 📊 Gantt | timeline اجراهای امروز |
| 🔍 جزئیات | تاریخچه step-level |

---

## تنظیمات

| متغیر | پیش‌فرض | توضیح |
|-------|---------|-------|
| `SQL_SERVER` | — | نام سرور |
| `SQL_USER` | — | نام کاربری |
| *(رمز)* | — | Windows Credential Manager |
| `DASH_HOST` | `127.0.0.1` | فقط دسترسی محلی |
| `REFRESH_RUNNING` | `15000` | بروزرسانی جاب‌های در حال اجرا (ms) |
| `REFRESH_HISTORY` | `60000` | بروزرسانی تاریخچه (ms) |

---

## License

MIT — contributions welcome.
