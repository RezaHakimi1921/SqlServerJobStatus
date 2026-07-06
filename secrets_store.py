"""Store SQL passwords in Windows Credential Manager (via keyring)."""

import keyring

SERVICE = "SqlServerAgentStatus"


def _account_key(server: str, user: str) -> str:
    return f"{server.strip()}|{user.strip()}"


def get_sql_password(server: str, user: str) -> str:
    if not server or not user:
        return ""
    return keyring.get_password(SERVICE, _account_key(server, user)) or ""


def set_sql_password(server: str, user: str, password: str) -> None:
    keyring.set_password(SERVICE, _account_key(server, user), password)


def delete_sql_password(server: str, user: str) -> None:
    try:
        keyring.delete_password(SERVICE, _account_key(server, user))
    except keyring.errors.PasswordDeleteError:
        pass
