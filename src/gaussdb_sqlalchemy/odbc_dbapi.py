"""DB-API bridge to pyodbc for GaussDB ODBC connections.

This module wraps pyodbc so it conforms to the DB-API 2.0 interface that
SQLAlchemy expects, and applies GaussDB-specific connection settings.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any

_DBAPI_MODULE = "pyodbc"

# Cache the loaded module so exception classes are stable references.
_dbapi: ModuleType | None = None


def _load_dbapi() -> ModuleType:
    """Import pyodbc lazily so the dialect can be registered without it."""
    global _dbapi
    if _dbapi is not None:
        return _dbapi
    try:
        _dbapi = import_module(_DBAPI_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name == _DBAPI_MODULE:
            raise ModuleNotFoundError(
                "pyodbc is not installed. Install it with 'pip install pyodbc'."
            ) from exc
        raise
    return _dbapi


import datetime as _dt
import re as _re


_DATE_RE = _re.compile(r"^(\d{1,4}-\d{1,2}-\d{1,2})(?:\s+00:00:00(?:\s+AD)?)?$")


def _bool_converter(value):
    """Convert ODBC boolean returns to Python True/False.

    The GaussDB ODBC driver may return 1/0, '1'/'0', b'\\x01'/b'\\x00',
    or 't'/'f' depending on the compatibility mode and driver version.
    """
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return value.strip() in ("1", "t", "true", "T", "TRUE")
    return bool(value)


def _date_converter(value):
    """Convert ODBC date returns to datetime.date.

    The GaussDB ODBC driver on Windows returns datetime.datetime
    instead of datetime.date for DATE columns.
    """
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, (bytes, bytearray)):
        s = value.decode("utf-8").strip()
        match = _DATE_RE.match(s)
        return _dt.date.fromisoformat(match.group(1) if match else s)
    if isinstance(value, str):
        s = value.strip()
        match = _DATE_RE.match(s)
        return _dt.date.fromisoformat(match.group(1) if match else s)
    return value


def _timestamp_converter(value):
    """Normalize ODBC timestamp returns to datetime.datetime."""
    if isinstance(value, (bytes, bytearray)):
        s = value.decode("utf-8").strip()
        return _dt.datetime.fromisoformat(s)
    if isinstance(value, str):
        return _dt.datetime.fromisoformat(value.strip())
    return value


def _text_converter(value):
    """Convert ODBC text returns to str, normalising CRLF."""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8").replace("\r\n", "\n")
    if isinstance(value, str):
        return value.replace("\r\n", "\n")
    return str(value)


def _normalise_output_value(value):
    if isinstance(value, str):
        return value.replace("\r\n", "\n")
    return value


def _normalise_output_row(row):
    if row is None:
        return None
    return tuple(_normalise_output_value(value) for value in row)


class _CursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, *args, **kwargs):
        self._cursor.execute(*args, **kwargs)
        return self

    def executemany(self, *args, **kwargs):
        self._cursor.executemany(*args, **kwargs)
        return self

    def fetchone(self):
        return _normalise_output_row(self._cursor.fetchone())

    def fetchmany(self, size=None):
        if size is None:
            return [_normalise_output_row(row) for row in self._cursor.fetchmany()]
        return [_normalise_output_row(row) for row in self._cursor.fetchmany(size)]

    def fetchall(self):
        return [_normalise_output_row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        for row in self._cursor:
            yield _normalise_output_row(row)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _ConnectionWrapper:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return _CursorWrapper(self._connection.cursor())

    @property
    def autocommit(self):
        return self._connection.autocommit

    @autocommit.setter
    def autocommit(self, value):
        self._connection.autocommit = value

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _patch_connection(conn):
    """Apply GaussDB-specific settings to a pyodbc connection.

    Registers output converters to normalise values that pyodbc / the
    GaussDB ODBC driver returns in formats different from what
    SQLAlchemy's PostgreSQL dialect expects.

    pyodbc's ``add_output_converter`` accepts **ODBC SQL type codes**
    (not PostgreSQL OIDs).  The key mappings:

    - ``SQL_BIT`` (-7)  → boolean
    - ``SQL_TYPE_DATE`` (-91) / ``SQL_DATE`` (9) → date
    - ``SQL_TYPE_TIMESTAMP`` (-93) / ``SQL_TIMESTAMP`` (11) → timestamp
    - ``SQL_LONGVARCHAR`` (-1) / ``SQL_VARCHAR`` (1) / ``SQL_WVARCHAR`` (-96) → text
    - ``SQL_BINARY`` (-2) / ``SQL_VARBINARY`` (-3) / ``SQL_LONGVARBINARY`` (-4) → bytes
    """
    # Ensure autocommit is off — SQLAlchemy manages transactions.
    conn.autocommit = False

    # --- Boolean: SQL_BIT (-7) ---
    # GaussDB ODBC driver may return int 1/0 for boolean columns.
    conn.add_output_converter(-7, _bool_converter)

    # --- Date: SQL_TYPE_DATE (-91) and SQL_DATE (9) ---
    # GaussDB ODBC driver on Windows returns datetime for DATE columns.
    conn.add_output_converter(-91, _date_converter)
    conn.add_output_converter(9, _date_converter)

    # --- Timestamp: SQL_TYPE_TIMESTAMP (-93) and SQL_TIMESTAMP (11) ---
    conn.add_output_converter(-93, _timestamp_converter)
    conn.add_output_converter(11, _timestamp_converter)

    # --- Text: SQL_LONGVARCHAR (-1), SQL_VARCHAR (1), SQL_WVARCHAR (-96) ---
    conn.add_output_converter(-1, _text_converter)
    conn.add_output_converter(1, _text_converter)
    conn.add_output_converter(-96, _text_converter)

    return _ConnectionWrapper(conn)


def connect(connection_string: str, **kwargs: Any):
    """Open an ODBC connection to GaussDB.

    Parameters
    ----------
    connection_string:
        Full ODBC connection string, e.g.::

            Driver={GaussDB ODBC Driver};
            Server=host;Port=port;Database=db;
            UID=user;PWD=password;SSLmode=disable;

    **kwargs:
        Additional keyword arguments passed through to ``pyodbc.connect``.
    """
    dbapi = _load_dbapi()
    conn = dbapi.connect(connection_string, **kwargs)
    return _patch_connection(conn)


def __getattr__(name: str) -> Any:
    """Proxy attribute access to the underlying pyodbc module.

    This exposes DB-API exception classes (Error, OperationalError, etc.)
    and constants (NUMBER, STRING, ...) so SQLAlchemy sees a compliant
    DB-API module.
    """
    return getattr(_load_dbapi(), name)


# DB-API 2.0 module-level attributes
apilevel = "2.0"
threadsafety = 1
paramstyle = "qmark"
