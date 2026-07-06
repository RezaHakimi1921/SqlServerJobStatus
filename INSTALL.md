# Installation Guide / راهنمای نصب

Complete setup on a **fresh Windows PC** with nothing pre-installed.

---

## Checklist (install in this order)

| # | Component | Required | Link |
|---|-----------|----------|------|
| 1 | **Python 3.9+** (64-bit) | Yes | https://www.python.org/downloads/ |
| 2 | **pip** (included with Python) | Yes | — |
| 3 | **ODBC Driver 17 or 18** for SQL Server | Yes | https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server |
| 4 | **SQL login** with SELECT on `msdb` | Yes | Ask your DBA |
| 5 | **Git** (optional, to clone repo) | No | https://git-scm.com/download/win |

---

## Step 1 — Install Python

1. Download **Python 3.11 or 3.12** from https://www.python.org/downloads/
2. Run the installer.
3. **Important — check these boxes:**
   - `[x] Add python.exe to PATH`
   - `[x] Install pip`
4. Click **Install Now**.

### Disable Windows Store alias (very common issue)

Windows may show *"Python was not found… Microsoft Store"* even after install.

1. Open **Settings** → **Apps** → **Advanced app settings**
2. Click **App execution aliases**
3. Turn **OFF**:
   - `python.exe`
   - `python3.exe`
4. Close all Command Prompt windows and open a **new** one.

### Verify Python

```bat
py --version
```

You should see something like `Python 3.12.x`.

---

## Step 2 — Clone or copy the project

```bat
git clone https://github.com/RezaHakimi1921/SqlServerJobStatus.git
cd SqlServerJobStatus
```

Or unzip the project folder.

---

## Step 3 — Run setup.bat

Double-click **`setup.bat`** or:

```bat
setup.bat
```

**No Python installed?** `setup.bat` will automatically download and install:

- Python 3.12 (via winget, or direct download from python.org)
- ODBC Driver 17 for SQL Server (via winget, or Microsoft MSI)

Internet access is required on first run.

It will also:

- Install Python packages from `requirements.txt`
- Verify ODBC drivers

---

## Step 4 — Run the app

```bat
run.bat
```

Browser opens at http://localhost:8050

On first run, open **Settings** and enter:

- SQL Server name / IP
- Username
- Password (stored in Windows Credential Manager, not in files)

---

## Step 5 — ODBC Driver (if setup warns)

Download and install **ODBC Driver 17 for SQL Server** (or 18):

https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

Run `setup.bat` again after install.

---

## SQL permissions needed

```sql
-- Example (run on SQL Server as admin)
USE msdb;
GRANT SELECT ON dbo.sysjobs TO [YourLogin];
GRANT SELECT ON dbo.sysjobsteps TO [YourLogin];
GRANT SELECT ON dbo.sysjobhistory TO [YourLogin];
GRANT SELECT ON dbo.sysjobactivity TO [YourLogin];
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Python was not found` | Install Python + disable Store aliases (Step 1) |
| `pip is not recognized` | Reinstall Python with "Install pip" checked |
| `IM002` ODBC error | Install ODBC Driver 17/18 |
| Port 8050 in use | Change `DASH_PORT` in `.env` |
| Blank page | Run `setup.bat` again |

---

# راهنمای فارسی (خلاصه)

1. **Python 3.9+** نصب کنید — حتماً `Add to PATH` را تیک بزنید  
2. **alias** های `python.exe` در تنظیمات ویندوز را خاموش کنید  
3. **`setup.bat`** را اجرا کنید  
4. **`run.bat`** را اجرا کنید  
5. در تنظیمات برنامه، Server / User / Password را وارد کنید  
6. اگر خطای ODBC دیدید، **ODBC Driver 17** را نصب کنید  

رمز عبور در فایل `.env` ذخیره **نمی‌شود** — فقط در Windows Credential Manager.
