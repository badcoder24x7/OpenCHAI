#!/usr/bin/env python3
"""
tests/test_inventory.py — Unit tests for inventory.py
Run with: python3 -m pytest tests/ -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inventory import (
    HostRecord,
    ParseError,
    ValidationError,
    HostNotFoundError,
    atomic_write,
    build_inventory_json,
    parse_inventory_file,
    validate_ip,
    validate_name,
    validate_port,
)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestValidateIp:
    def test_valid(self):
        assert validate_ip("192.168.1.10") == "192.168.1.10"

    def test_invalid(self):
        with pytest.raises(ValidationError):
            validate_ip("999.999.999.999")

    def test_hostname_rejected(self):
        with pytest.raises(ValidationError):
            validate_ip("master01")


class TestValidatePort:
    def test_valid(self):
        assert validate_port("22") == 22
        assert validate_port("4411") == 4411

    def test_zero(self):
        with pytest.raises(ValidationError):
            validate_port("0")

    def test_too_large(self):
        with pytest.raises(ValidationError):
            validate_port("99999")

    def test_non_numeric(self):
        with pytest.raises(ValidationError):
            validate_port("ssh")


class TestValidateName:
    def test_valid(self):
        assert validate_name("master01", "node") == "master01"
        assert validate_name("hpc_master", "group") == "hpc_master"
        assert validate_name("cn-001", "hostname") == "cn-001"

    def test_empty(self):
        with pytest.raises(ValidationError):
            validate_name("", "node")

    def test_special_chars(self):
        with pytest.raises(ValidationError):
            validate_name("node;rm -rf /", "node")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

VALID_INV = textwrap.dedent("""\
    # comment
    master01 192.168.10.11 root hpc_master master01 22
    compute001 192.168.10.101 root compute cn001 22
    gpu001 192.168.20.10 root gpu gpu001 4411
""")

class TestParseInventoryFile:
    def _write(self, content: str) -> Path:
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.write(fd, content.encode())
        os.close(fd)
        return Path(path)

    def test_valid(self):
        p = self._write(VALID_INV)
        records, warnings = parse_inventory_file(p)
        assert len(records) == 3
        assert warnings == []
        assert records[0].node == "master01"
        assert records[2].ssh_port == 4411

    def test_duplicate_node_skipped(self):
        content = VALID_INV + "master01 192.168.10.200 root hpc_master master01 22\n"
        p = self._write(content)
        records, warnings = parse_inventory_file(p)
        assert len(records) == 3
        assert any("duplicate node" in w.lower() for w in warnings)

    def test_duplicate_ip_skipped(self):
        content = VALID_INV + "extra01 192.168.10.11 root compute extra01 22\n"
        p = self._write(content)
        records, warnings = parse_inventory_file(p)
        assert len(records) == 3
        assert any("duplicate ip" in w.lower() for w in warnings)

    def test_seven_field_rejected(self):
        content = "master01 192.168.10.11 root hpc_master master01 22 Secret\n"
        p = self._write(content)
        with pytest.raises(ParseError, match="password field"):
            parse_inventory_file(p)

    def test_bad_ip_skipped(self):
        content = VALID_INV + "bad01 not_an_ip root compute bad01 22\n"
        p = self._write(content)
        records, warnings = parse_inventory_file(p)
        assert len(records) == 3
        assert any("not_an_ip" in w or "bad01" in w for w in warnings)

    def test_missing_file(self):
        with pytest.raises(ParseError):
            parse_inventory_file(Path("/nonexistent/file.txt"))


# ---------------------------------------------------------------------------
# Inventory JSON builder
# ---------------------------------------------------------------------------

class TestBuildInventoryJson:
    def test_structure(self):
        records = [
            HostRecord("master01", "192.168.1.1", "root", "hpc_master", "master01", 22),
            HostRecord("cn001", "192.168.1.2", "root", "compute", "cn001", 22),
        ]
        inv = build_inventory_json(records)
        assert "_meta" in inv
        assert "hostvars" in inv["_meta"]
        assert "master01" in inv["_meta"]["hostvars"]
        assert "hpc_master" in inv
        assert "master01" in inv["hpc_master"]["hosts"]

    def test_no_passwords_in_hostvars(self):
        records = [
            HostRecord("master01", "192.168.1.1", "root", "hpc_master", "master01", 22),
        ]
        inv = build_inventory_json(records)
        hv = inv["_meta"]["hostvars"]["master01"]
        # password / ansible_password must not appear
        for key in hv:
            assert "password" not in key.lower()
        for val in hv.values():
            assert isinstance(val, (str, int))


# ---------------------------------------------------------------------------
# HostRecord
# ---------------------------------------------------------------------------

class TestHostRecord:
    def test_to_inventory_line_no_password(self):
        r = HostRecord("n1", "10.0.0.1", "root", "g1", "h1", 22)
        line = r.to_inventory_line()
        assert "password" not in line.lower()
        parts = line.split()
        assert len(parts) == 6

    def test_to_hostvars_no_password(self):
        r = HostRecord("n1", "10.0.0.1", "root", "g1", "h1", 4411)
        hv = r.to_hostvars()
        assert hv["ansible_port"] == 4411
        for k in hv:
            assert "password" not in k.lower()


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        dest = tmp_path / "out.txt"
        atomic_write(dest, "hello world\n")
        assert dest.read_text() == "hello world\n"

    def test_overwrites_atomically(self, tmp_path):
        dest = tmp_path / "out.txt"
        dest.write_text("old")
        atomic_write(dest, "new")
        assert dest.read_text() == "new"

    def test_creates_parent_dirs(self, tmp_path):
        dest = tmp_path / "a" / "b" / "c.txt"
        atomic_write(dest, "x")
        assert dest.read_text() == "x"
