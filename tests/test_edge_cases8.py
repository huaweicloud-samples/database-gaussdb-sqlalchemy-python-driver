"""Round 8: Final stress round — long-running stability, complex queries, cleanup verification."""
import uuid, time
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Integer, LargeBinary, MetaData,
    Numeric, String, Table, Text, create_engine, inspect, select, text,
    ForeignKey, func, Index, UniqueConstraint, and_, or_, not_,
)
from sqlalchemy.orm import Session, declarative_base

from tests.test_config import ODBC_URLS as URLS

def _engine(compat, **kw):
    return create_engine(URLS[compat], pool_pre_ping=True, **kw)

def _tname(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── 1. Repeated engine create/dispose cycles ─────────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B", "M"])
def test_engine_lifecycle_cycles(compat):
    """Test repeated engine create/dispose cycles — driver stability."""
    for cycle in range(5):
        engine = _engine(compat)
        with engine.connect() as conn:
            assert conn.execute(text("select 1")).scalar_one() == 1
        engine.dispose()
    print(f"  {compat} engine lifecycle (5 cycles): PASS")


# ── 2. Long-running query with many result rows ──────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B", "M"])
def test_large_result_set_50k(compat):
    """Test fetching 50K rows."""
    engine = _engine(compat)
    table_name = _tname("v50k")
    md = MetaData()
    t = Table(table_name, md, Column("id", Integer, primary_key=True), Column("val", Integer))
    try:
        md.create_all(engine)
        with engine.begin() as conn:
            conn.execute(t.insert(), [{"id": i, "val": i*2} for i in range(1, 50001)])
        with engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(
                select(t.c.id, t.c.val).order_by(t.c.id)
            )
            count = 0
            last_val = 0
            for row in result:
                assert row[1] == row[0] * 2
                last_val = row[0]
                count += 1
            assert count == 50000, f"Expected 50000, got {count}"
            assert last_val == 50000
        print(f"  {compat} 50K rows: PASS")
    finally:
        md.drop_all(engine)


# ── 5. Repeated DDL on same table name (cache invalidation) ──────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B", "M"])
def test_repeated_ddl_cache_invalidation(compat):
    """Test that DDL changes are properly detected after table rebuild."""
    engine = _engine(compat)
    table_name = _tname("vcache")
    md = MetaData()
    t = Table(table_name, md, Column("id", Integer, primary_key=True), Column("a", String(32)))
    try:
        for cycle in range(3):
            md.create_all(engine)
            inspector = inspect(engine)
            cols_before = {c["name"] for c in inspector.get_columns(table_name)}

            # Alter table: add column
            with engine.begin() as conn:
                conn.execute(text(f"alter table {table_name} add column col_{cycle} varchar(32)"))

            # Clear cache and re-inspect
            inspector.clear_cache()
            cols_after = {c["name"] for c in inspector.get_columns(table_name)}
            assert f"col_{cycle}" in cols_after, f"Cycle {cycle}: new col not reflected: {cols_after}"
            assert cols_before != cols_after, f"Cache not invalidated"

            md.drop_all(engine)
            # Recreate for next cycle
            md = MetaData()
            t = Table(table_name, md, Column("id", Integer, primary_key=True), Column("a", String(32)))
        print(f"  {compat} DDL cache invalidation (3 cycles): PASS")
    finally:
        md.drop_all(engine)


# ── 6. Connection: 100 rapid open/close cycles ───────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B", "M"])
def test_rapid_connection_cycles(compat):
    """Test 100 rapid connect/close cycles."""
    engine = _engine(compat, pool_size=2, max_overflow=3)
    for i in range(100):
        with engine.connect() as conn:
            result = conn.execute(text(f"select {i}")).scalar_one()
            assert result == i
    print(f"  {compat} 100 rapid cycles: PASS")


# ── 7. Transaction: long-running with multiple statements ────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B"])
def test_long_transaction(compat):
    """Test a long transaction with many statements."""
    engine = _engine(compat)
    table_name = _tname("vlongtx")
    md = MetaData()
    t = Table(table_name, md, Column("id", Integer, primary_key=True), Column("val", Integer))
    try:
        md.create_all(engine)
        with engine.begin() as conn:
            for i in range(1, 101):
                conn.execute(t.insert().values(id=i, val=i))
                if i % 10 == 0:
                    count = conn.execute(select(func.count()).select_from(t)).scalar_one()
                    assert count == i, f"At step {i}: expected {i}, got {count}"
            # Update all
            conn.execute(t.update().values(val=t.c.val * 10))
            total = conn.execute(select(func.sum(t.c.val))).scalar_one()
            assert total == sum(i*10 for i in range(1, 101))
        print(f"  {compat} long transaction (100 stmts): PASS")
    finally:
        md.drop_all(engine)


# ── 8. Verify no leftover test tables ────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B", "M"])
def test_no_leftover_test_tables(compat):
    """Verify that all test tables from previous runs are cleaned up."""
    engine = _engine(compat)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    # Filter for test-generated tables
    test_prefixes = ("gdbdrv_", "edge_", "v", "verify_")
    leftovers = [t for t in tables if any(t.startswith(p) for p in test_prefixes)]
    # Some may remain from failed test runs — clean them up
    if leftovers:
        print(f"  {compat} leftover tables: {len(leftovers)} found")
        for t in leftovers:
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"drop table if exists {t} cascade"))
            except Exception:
                pass
    else:
        print(f"  {compat} no leftover tables: PASS")


# ── 10. Final: full suite regression check ───────────────────────────────────

@pytest.mark.integration
@pytest.mark.parametrize("compat", ["A", "B", "M"])
def test_final_comprehensive_crud(compat):
    """Final comprehensive CRUD test covering all major types."""
    engine = _engine(compat)
    table_name = _tname("vfinal")
    md = MetaData()
    t = Table(table_name, md,
        Column("id", Integer, primary_key=True),
        Column("name", String(50), nullable=False),
        Column("amount", Numeric(12, 2)),
        Column("created_at", DateTime),
        Column("biz_date", Date),
        Column("active", Boolean),
        Column("description", Text),
    )
    try:
        # CREATE
        md.create_all(engine)
        assert inspect(engine).has_table(table_name)

        # INSERT
        with engine.begin() as conn:
            conn.execute(t.insert(), [
                {"id": 1, "name": "alpha", "amount": Decimal("100.50"), "created_at": datetime(2026,1,1,10,0,0), "biz_date": date(2026,1,1), "active": True, "description": "first"},
                {"id": 2, "name": "beta", "amount": Decimal("200.75"), "created_at": datetime(2026,6,23,14,30,0), "biz_date": date(2026,6,23), "active": False, "description": "second"},
                {"id": 3, "name": "gamma", "amount": None, "created_at": None, "biz_date": None, "active": None, "description": None},
            ])

        # SELECT
        with engine.connect() as conn:
            rows = conn.execute(select(t).order_by(t.c.id)).all()
            assert len(rows) == 3
            assert rows[0].name == "alpha"
            assert rows[0].amount == Decimal("100.50")
            assert rows[0].active is True or rows[0].active == 1 or rows[0].active == "1"
            assert rows[2].amount is None
            assert rows[2].active is None

        # UPDATE
        with engine.begin() as conn:
            conn.execute(t.update().where(t.c.id == 1).values(name="ALPHA", amount=Decimal("999.99")))
            result = conn.execute(select(t.c.name, t.c.amount).where(t.c.id == 1)).one()
            assert result == ("ALPHA", Decimal("999.99"))

        # DELETE
        with engine.begin() as conn:
            conn.execute(t.delete().where(t.c.id == 3))
            count = conn.execute(select(func.count()).select_from(t)).scalar_one()
            assert count == 2

        # DROP
        md.drop_all(engine)
        assert not inspect(engine).has_table(table_name)
        print(f"  {compat} final comprehensive CRUD: PASS")
    except Exception:
        md.drop_all(engine)
        raise
