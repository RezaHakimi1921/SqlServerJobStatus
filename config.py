import getpass
import os
import subprocess
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from secrets_store import get_sql_password, set_sql_password

ENV_PATH = Path(__file__).parent / ".env"

_SQL_KEYS = frozenset({
    "SQL_SERVER", "SQL_DATABASE", "SQL_USER", "SQL_PASSWORD",
    "SQL_DRIVER", "SQL_TIMEOUT", "SQL_ENCRYPT", "SQL_TRUST_CERT",
})

_MIGRATED = False


def _escape_odbc_value(value: str) -> str:
    if not value:
        return value
    if any(ch in value for ch in (";", "{", "}", "=")):
        return "{" + value.replace("}", "}}") + "}"
    return value


def _harden_env_file() -> None:
    if os.name != "nt" or not ENV_PATH.exists():
        return
    user = os.environ.get("USERNAME") or getpass.getuser()
    subprocess.run(
        ["icacls", str(ENV_PATH), "/inheritance:r", "/grant:r", f"{user}:F"],
        capture_output=True,
        check=False,
    )


def _strip_password_from_env_file() -> None:
    if not ENV_PATH.exists():
        return
    lines = []
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("SQL_PASSWORD="):
            lines.append("# SQL_PASSWORD is stored in Windows Credential Manager")
        else:
            lines.append(line)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def migrate_legacy_password() -> None:
    """Move plaintext SQL_PASSWORD from .env into Windows Credential Manager."""
    global _MIGRATED
    if _MIGRATED:
        return
    _MIGRATED = True

    load_dotenv(ENV_PATH, override=True)
    server = os.getenv("SQL_SERVER", "").strip()
    user = os.getenv("SQL_USER", "").strip()
    legacy = os.getenv("SQL_PASSWORD", "")
    if legacy and server and user:
        set_sql_password(server, user, legacy)
        _strip_password_from_env_file()
        load_dotenv(ENV_PATH, override=True)


def load_config():
    migrate_legacy_password()
    load_dotenv(ENV_PATH, override=True)
    server = os.getenv("SQL_SERVER", "").strip()
    user = os.getenv("SQL_USER", "").strip()
    password = get_sql_password(server, user)
    if not password:
        password = os.getenv("SQL_PASSWORD", "")
    refresh_raw = os.getenv("REFRESH_MINUTES", "5").strip()
    try:
        refresh_minutes = int(refresh_raw)
    except ValueError:
        refresh_minutes = 5
    if refresh_minutes not in (1, 5, 10, 30, 60):
        refresh_minutes = 5
    return {
        "server": server,
        "database": os.getenv("SQL_DATABASE", "msdb").strip() or "msdb",
        "user": user,
        "password": password,
        "driver": os.getenv("SQL_DRIVER", "17").strip(),
        "timeout": int(os.getenv("SQL_TIMEOUT", "10")),
        "encrypt": os.getenv("SQL_ENCRYPT", "no").strip(),
        "trust_cert": os.getenv("SQL_TRUST_CERT", "yes").strip(),
        "refresh_minutes": refresh_minutes,
    }


def is_configured():
    c = load_config()
    return bool(c["server"] and c["user"] and c["password"])


def _is_blank_password(value) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    if not s:
        return True
    return all(c in "•●*·." for c in s)


def resolve_password(server: str, user: str, password_input: Optional[str]) -> str:
    """Use keyring when field is empty or contains only mask characters."""
    if password_input and not _is_blank_password(password_input):
        return str(password_input).strip()
    stored = get_sql_password(server or "", user or "")
    if stored:
        return stored
    cfg = load_config()
    if (
        cfg.get("server", "").strip() == (server or "").strip()
        and cfg.get("user", "").strip() == (user or "").strip()
    ):
        return cfg.get("password") or ""
    return ""


def resolve_odbc_driver(driver=None) -> str:
    """Return an installed ODBC driver name (exact string for DRIVER=)."""
    import pyodbc

    available = list(pyodbc.drivers())
    sql_drivers = [d for d in available if "SQL Server" in d]

    def pick_preferred() -> str:
        for name in (
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 13 for SQL Server",
            "SQL Server Native Client 11.0",
            "SQL Server",
        ):
            if name in available:
                return name
        if sql_drivers:
            return sql_drivers[0]
        raise RuntimeError(
            "هیچ ODBC Driver برای SQL Server نصب نیست. "
            "ODBC Driver 17 یا 18 را از مایکروسافت نصب کنید."
        )

    if driver is None or str(driver).strip() == "":
        stored = load_config().get("driver", "").strip()
        if stored:
            return resolve_odbc_driver(stored)
        return pick_preferred()

    s = str(driver).strip()
    if s in available:
        return s
    if s.isdigit():
        candidate = f"ODBC Driver {s} for SQL Server"
        if candidate in available:
            return candidate
    for d in sql_drivers:
        if s in d:
            return d
    return pick_preferred()


def list_sql_driver_options():
    """Options for settings dropdown: value = short version, label = full driver name."""
    import pyodbc

    opts = []
    for name in pyodbc.drivers():
        if "SQL Server" not in name:
            continue
        short = name.replace("ODBC Driver ", "").replace(" for SQL Server", "").strip()
        value = short if short.isdigit() else name
        opts.append({"label": name, "value": value})
    if not opts:
        opts = [{"label": "ODBC Driver 17 for SQL Server", "value": "17"}]
    return opts


def build_conn_str(config=None):
    c = config or load_config()
    driver = resolve_odbc_driver(c.get("driver"))
    encrypt = "yes" if c.get("encrypt", "no").lower() in ("yes", "true", "1") else "no"
    trust = "yes" if c.get("trust_cert", "yes").lower() in ("yes", "true", "1") else "no"
    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={_escape_odbc_value(c['server'])};"
        f"DATABASE={_escape_odbc_value(c['database'])};"
        f"UID={_escape_odbc_value(c['user'])};"
        f"PWD={_escape_odbc_value(c['password'])};"
        f"TrustServerCertificate={trust};"
        f"Encrypt={encrypt};"
        f"Connection Timeout={c['timeout']};"
    )


def _read_preserved_env():
    preserved = {}
    if not ENV_PATH.exists():
        return preserved
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in _SQL_KEYS:
            preserved[key] = value.strip()
    return preserved


def save_config(server, user, password, database="msdb", driver="17", timeout=10):
    set_sql_password(server, user, password)

    preserved = _read_preserved_env()
    existing = load_config()
    encrypt = existing.get("encrypt", "no")
    trust = existing.get("trust_cert", "yes")

    lines = [
        f"SQL_SERVER={server.strip()}",
        f"SQL_DATABASE={(database or 'msdb').strip()}",
        f"SQL_USER={user.strip()}",
        "# SQL_PASSWORD is stored in Windows Credential Manager",
        f"SQL_DRIVER={str(driver).strip()}",
        f"SQL_TIMEOUT={timeout}",
        f"SQL_ENCRYPT={encrypt}",
        f"SQL_TRUST_CERT={trust}",
    ]
    defaults = {
        "REFRESH_MINUTES": "5",
        "DASH_HOST": "127.0.0.1",
        "DASH_PORT": "8050",
    }
    written = {line.split("=", 1)[0].lstrip("# ").strip() for line in lines}
    for key, value in preserved.items():
        if key not in written:
            lines.append(f"{key}={value}")
            written.add(key)
    for key, value in defaults.items():
        if key not in written:
            lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _harden_env_file()
    load_dotenv(ENV_PATH, override=True)


def save_refresh_minutes(minutes: int) -> None:
    minutes = int(minutes)
    if minutes not in (1, 5, 10, 30, 60):
        minutes = 5
    lines = []
    found = False
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("REFRESH_MINUTES="):
                lines.append(f"REFRESH_MINUTES={minutes}")
                found = True
            elif stripped.startswith("REFRESH_INTERVAL="):
                continue  # legacy ms key — drop in favour of REFRESH_MINUTES
            else:
                lines.append(line)
    if not found:
        lines.append(f"REFRESH_MINUTES={minutes}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if ENV_PATH.exists():
        _harden_env_file()
    load_dotenv(ENV_PATH, override=True)


def test_connection(server, user, password, database="msdb", driver="17", timeout=10):
    import pyodbc

    resolved = resolve_password(server, user, password)
    cfg = {
        "server": server.strip(),
        "database": (database or "msdb").strip(),
        "user": user.strip(),
        "password": resolved,
        "driver": driver,
        "timeout": timeout,
        "encrypt": load_config().get("encrypt", "no"),
        "trust_cert": load_config().get("trust_cert", "yes"),
    }
    try:
        conn = pyodbc.connect(build_conn_str(cfg), timeout=timeout)
        cur = conn.cursor()
        cur.execute("SELECT DB_NAME()")
        db_name = cur.fetchone()[0]
        conn.close()
        return True, f"اتصال موفق — دیتابیس: {db_name}"
    except pyodbc.Error as ex:
        if ex.args and str(ex.args[0]) == "IM002":
            installed = [d for d in pyodbc.drivers() if "SQL Server" in d]
            tried = resolve_odbc_driver(driver)
            hint = "، ".join(installed) if installed else "هیچ درایوری یافت نشد"
            return False, f"ODBC Driver یافت نشد ({tried}). نصب‌شده: {hint}"
        raise
