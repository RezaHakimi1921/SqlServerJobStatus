"""Verify runtime dependencies after pip install."""
import sys


def main() -> int:
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    errors = 0

    for pkg in ("dash", "plotly", "pyodbc", "dotenv", "keyring"):
        try:
            __import__("dotenv" if pkg == "dotenv" else pkg)
            print(f"  OK  {pkg}")
        except ImportError:
            print(f"  FAIL  {pkg} - run setup.bat again")
            errors += 1

    try:
        import pyodbc

        sql_drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
        if sql_drivers:
            print("ODBC drivers:", ", ".join(sql_drivers))
        else:
            print("WARNING: No SQL Server ODBC driver found.")
            print("  Install ODBC Driver 17 or 18:")
            print("  https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server")
    except Exception as exc:
        print(f"WARNING: Could not list ODBC drivers: {exc}")

    if errors:
        print("\nSetup incomplete - fix errors above and re-run setup.bat")
        return 1

    print("\nAll Python packages OK. Run run.bat to start the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
