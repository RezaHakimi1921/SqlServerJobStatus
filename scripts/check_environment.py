"""Verify runtime prerequisites after pip install."""
import sys


def main() -> int:
    errors = []
    warnings = []

    if sys.version_info < (3, 9):
        errors.append(f"Python 3.9+ required (found {sys.version.split()[0]})")

    try:
        import dash  # noqa: F401
    except ImportError:
        errors.append("Package 'dash' not installed — run setup.bat")

    try:
        import pyodbc  # noqa: F401
    except ImportError:
        errors.append("Package 'pyodbc' not installed — run setup.bat")
    else:
        import pyodbc

        drivers = [d for d in pyodbc.drivers() if "SQL Server" in d]
        if not drivers:
            warnings.append(
                "No ODBC Driver for SQL Server found. "
                "Install ODBC Driver 17 or 18, then run install-prerequisites.bat"
            )
        else:
            print("OK  Python", sys.version.split()[0])
            print("OK  ODBC drivers:", ", ".join(drivers))

    for w in warnings:
        print("WARN", w)
    for e in errors:
        print("ERROR", e)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
