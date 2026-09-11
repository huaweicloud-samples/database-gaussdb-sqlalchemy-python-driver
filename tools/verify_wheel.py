"""Check that the delivered wheel contains this branch's dialect, not drivers."""
from configparser import ConfigParser
from email.parser import BytesParser
import hashlib
from pathlib import Path
import sys
from zipfile import ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    wheel = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        root / "packages/gaussdb_sqlalchemy-0.1.0-py3-none-any.whl"
    )
    modules = {"__init__.py", "base.py", "types.py", "alembic.py"}
    info = "gaussdb_sqlalchemy-0.1.0.dist-info/"
    expected = {"gaussdb_sqlalchemy/" + name for name in modules}
    with ZipFile(wheel) as archive:
        members = set(archive.namelist())
        assert {name for name in members if not name.startswith(info)} == expected
        for name in modules:
            assert archive.read("gaussdb_sqlalchemy/" + name) == (
                root / "src/gaussdb_sqlalchemy" / name
            ).read_bytes(), f"Runtime source mismatch: {name}"
        assert archive.read(info + "licenses/LICENSE.txt") == (root / "LICENSE.txt").read_bytes()
        metadata = BytesParser().parsebytes(archive.read(info + "METADATA"))
        assert metadata["Name"] == "gaussdb-sqlalchemy"
        assert metadata["Version"] == "0.1.0"
        assert metadata["Requires-Python"] == ">=3.9"
        assert metadata["License-Expression"] == "LGPL-3.0-only"
        assert metadata.get_payload(decode=True).decode("utf-8").rstrip() == (
            root / "README.md"
        ).read_text(encoding="utf-8").rstrip()
        assert not any("pyodbc" in req for req in metadata.get_all("Requires-Dist", []))
        entries = ConfigParser()
        entries.read_string(archive.read(info + "entry_points.txt").decode())
        assert dict(entries["sqlalchemy.dialects"]) == {
            "gaussdb": "gaussdb_sqlalchemy.base:GaussDBDialect",
            "gaussdb.psycopg": "gaussdb_sqlalchemy.base:GaussDBDialect",
            "gaussdb.gaussdb": "gaussdb_sqlalchemy.base:GaussDBDialect",
            "gaussdb.psycopg2": "gaussdb_sqlalchemy.base:GaussDBDialect_psycopg2",
        }
    print("Wheel source, license, README and four entry points verified.")
    print("SHA256:", hashlib.sha256(wheel.read_bytes()).hexdigest())
    print("Bytes:", wheel.stat().st_size)


if __name__ == "__main__":
    main()
