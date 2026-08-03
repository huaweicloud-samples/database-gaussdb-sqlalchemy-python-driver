"""Unit tests for the ODBC dialect layer."""

import sys
import types

import pytest
from sqlalchemy import Column
from sqlalchemy import Enum
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import Table
from sqlalchemy.engine import make_url

from gaussdb_sqlalchemy import odbc_dbapi
from gaussdb_sqlalchemy.odbc import GaussDBDialect_odbc
from gaussdb_sqlalchemy.odbc import _cast_enum_placeholders
from gaussdb_sqlalchemy.odbc import _convert_parameter
from gaussdb_sqlalchemy.odbc import _convert_parameters


# ------------------------------------------------------------------
# create_connect_args
# ------------------------------------------------------------------

def test_create_connect_args_builds_dsn_less_connection_string():
    dialect = GaussDBDialect_odbc()

    args, kwargs = dialect.create_connect_args(
        make_url(
            "gaussdb+odbc://scott:tiger@db.example.com:19995/postgres"
            "?driver=GaussDB+ODBC+Driver&sslmode=disable"
        )
    )

    assert kwargs == {}
    conn_str = args[0]
    assert "Driver={GaussDB ODBC Driver}" in conn_str
    assert "Server=db.example.com" in conn_str
    assert "Port=19995" in conn_str
    assert "Database=postgres" in conn_str
    assert "UID=scott" in conn_str
    assert "PWD=tiger" in conn_str
    assert "SSLmode=disable" in conn_str
    assert conn_str.endswith(";")


def test_create_connect_args_uses_default_driver_name():
    dialect = GaussDBDialect_odbc()

    args, _ = dialect.create_connect_args(
        make_url("gaussdb+odbc://scott:tiger@localhost:19995/testdb")
    )

    assert "Driver={GaussDB ODBC Driver}" in args[0]


def test_create_connect_args_supports_dsn_mode():
    dialect = GaussDBDialect_odbc()

    args, _ = dialect.create_connect_args(
        make_url("gaussdb+odbc://scott:tiger@/mydb?dsn=MyGaussDB")
    )

    conn_str = args[0]
    assert "DSN=MyGaussDB" in conn_str
    assert "Driver=" not in conn_str
    assert "Database=mydb" in conn_str
    assert "UID=scott" in conn_str
    assert "PWD=tiger" in conn_str


def test_create_connect_args_forwards_extra_query_params():
    dialect = GaussDBDialect_odbc()

    args, _ = dialect.create_connect_args(
        make_url(
            "gaussdb+odbc://scott:tiger@host:19995/db"
            "?driver=MyDriver&UseServerSidePrepare=1&sslmode=disable"
        )
    )

    conn_str = args[0]
    assert "Driver={MyDriver}" in conn_str
    assert "UseServerSidePrepare=1" in conn_str


# ------------------------------------------------------------------
# import_dbapi
# ------------------------------------------------------------------

def test_import_dbapi_returns_odbc_dbapi_module():
    module = GaussDBDialect_odbc.import_dbapi()
    assert module is odbc_dbapi
    assert module.apilevel == "2.0"
    assert module.paramstyle == "qmark"


def test_dbapi_connect_sets_autocommit_false(monkeypatch):
    class FakeConnection:
        autocommit = True

        def add_output_converter(self, sql_type, func):
            pass  # mock: accept any output converter registration

    class FakePyodbc:
        def connect(self, conn_str, **kw):
            assert "Driver=" in conn_str
            return FakeConnection()

    monkeypatch.setitem(sys.modules, "pyodbc", FakePyodbc())
    odbc_dbapi._dbapi = None  # reset cache

    conn = odbc_dbapi.connect("Driver={GaussDB ODBC Driver};UID=x;")
    assert conn.autocommit is False


def test_dbapi_cursor_wrapper_normalises_text_rows(monkeypatch):
    class FakeCursor:
        def __init__(self):
            self.description = [("val",)]

        def execute(self, *args, **kwargs):
            return self

        def fetchone(self):
            return ("line1\r\nline2",)

        def fetchall(self):
            return [("a\r\nb",), ("c",)]

        def fetchmany(self, size=None):
            return [("x\r\ny",)]

        def __iter__(self):
            return iter([("i\r\nj",)])

    class FakeConnection:
        autocommit = True

        def add_output_converter(self, sql_type, func):
            pass

        def cursor(self):
            return FakeCursor()

    class FakePyodbc:
        def connect(self, conn_str, **kw):
            return FakeConnection()

    monkeypatch.setitem(sys.modules, "pyodbc", FakePyodbc())
    odbc_dbapi._dbapi = None

    cursor = odbc_dbapi.connect("Driver={x};").cursor()

    assert cursor.execute("select 1") is cursor
    assert cursor.description == [("val",)]
    assert cursor.fetchone() == ("line1\nline2",)
    assert cursor.fetchall() == [("a\nb",), ("c",)]
    assert cursor.fetchmany() == [("x\ny",)]
    assert list(cursor) == [("i\nj",)]


def test_dbapi_raises_actionable_error_when_pyodbc_missing(monkeypatch):
    def missing_module(name, *args, **kwargs):
        raise ModuleNotFoundError("No module named 'pyodbc'", name=name)

    monkeypatch.setattr(odbc_dbapi, "import_module", missing_module)
    odbc_dbapi._dbapi = None

    with pytest.raises(ModuleNotFoundError, match="pip install pyodbc"):
        odbc_dbapi.connect("Driver={x};")


def test_date_converter_accepts_windows_odbc_ad_suffix():
    from datetime import date

    assert odbc_dbapi._date_converter("2026-06-18 00:00:00 AD") == date(2026, 6, 18)
    assert odbc_dbapi._date_converter(b"2026-06-18 00:00:00 AD") == date(2026, 6, 18)


# ------------------------------------------------------------------
# Parameter conversion
# ------------------------------------------------------------------

def test_convert_parameters_passthrough_for_tuple():
    from datetime import datetime
    from decimal import Decimal

    original = (1, "hello", datetime(2026, 1, 1), Decimal("3.14"), b"bytes")
    converted = _convert_parameters(original)
    assert converted == (1, "hello", "2026-01-01 00:00:00.000000", Decimal("3.14"), b"bytes")


def test_convert_parameters_none():
    assert _convert_parameters(None) is None


def test_convert_parameters_list():
    assert _convert_parameters([1, 2, 3]) == [1, 2, 3]


def test_convert_parameter_passthrough_except_datetime():
    from datetime import date
    from datetime import datetime
    from decimal import Decimal

    assert _convert_parameter(42) == 42
    assert _convert_parameter("str") == "str"
    assert _convert_parameter(date(2026, 1, 1)) == date(2026, 1, 1)
    assert _convert_parameter(datetime(2026, 1, 1, 1, 2, 3, 4)) == (
        "2026-01-01 01:02:03.000004"
    )
    assert _convert_parameter(Decimal("1.5")) == Decimal("1.5")
    assert _convert_parameter(b"\x00\x01") == b"\x00\x01"


def test_convert_parameter_timezone_aware_datetime_to_naive_utc():
    from datetime import datetime
    from datetime import timedelta
    from datetime import timezone

    value = datetime(2026, 6, 23, 20, 0, 0, 123456, tzinfo=timezone(timedelta(hours=8)))

    assert _convert_parameter(value) == "2026-06-23 12:00:00.123456"


# ------------------------------------------------------------------
# Enum cast
# ------------------------------------------------------------------

def test_cast_enum_placeholders_no_context():
    assert _cast_enum_placeholders("SELECT ?", None) == "SELECT ?"


def test_cast_enum_placeholders_with_enum():
    d = GaussDBDialect_odbc()
    # Initialize the dialect so identifier_preparer is available
    d._compiled_cache = {}
    # PGDialect creates identifier_preparer in __init__, but it needs type_compiler
    from sqlalchemy.dialects.postgresql.base import PGIdentifierPreparer
    d.identifier_preparer = PGIdentifierPreparer(d)

    metadata = MetaData()
    table = Table(
        "t", metadata,
        Column("id", Integer),
        Column("status", Enum("active", "inactive", name="user_status")),
    )

    class FakeBind:
        def __init__(self, type_):
            self.type = type_

    class FakeCompiled:
        positiontup = ["id", "status"]
        binds = {"id": FakeBind(Integer()), "status": FakeBind(table.c.status.type)}

    class FakeContext:
        compiled = FakeCompiled()
        dialect = d

    result = _cast_enum_placeholders("INSERT INTO t VALUES (?, ?)", FakeContext())
    assert "::user_status" in result


def test_cast_enum_placeholders_non_native_enum_no_cast():
    d = GaussDBDialect_odbc()
    non_native = Enum("a", "b", native_enum=False, name="nr")

    class FakeBind:
        def __init__(self, type_):
            self.type = type_

    class FakeCompiled:
        positiontup = ["val"]
        binds = {"val": FakeBind(non_native)}

    class FakeContext:
        compiled = FakeCompiled()
        dialect = d

    result = _cast_enum_placeholders("SELECT ?", FakeContext())
    assert result == "SELECT ?"


# ------------------------------------------------------------------
# Registry
# ------------------------------------------------------------------

def test_dialect_registered_as_gaussdb_and_gaussdb_odbc():
    from sqlalchemy.dialects import registry
    from sqlalchemy.engine.url import make_url

    # gaussdb:// should resolve to ODBC dialect
    url = make_url("gaussdb://user:pass@host:19995/db")
    cls = url._get_entrypoint()
    assert cls is GaussDBDialect_odbc

    # gaussdb+odbc:// — SQLAlchemy converts "+" to "." for registry lookup
    url2 = make_url("gaussdb+odbc://user:pass@host:19995/db")
    cls2 = url2._get_entrypoint()
    assert cls2 is GaussDBDialect_odbc
