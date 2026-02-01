"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.

    pp-terminal is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    pp-terminal is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with pp-terminal. If not, see <http://www.gnu.org/licenses/>.
"""

from pathlib import Path

import pytest

from pp_terminal.utils.cache import get_cache_path


def test_cache_path_format(tmp_path: Path) -> None:
    """Test that cache path has correct format."""
    xml_file = tmp_path / "test.xml"
    xml_file.write_text("<?xml version='1.0'?><test>data</test>")

    cache_path = get_cache_path(xml_file)

    # Verify format: .{xml-name}.{checksum}.pp-terminal.db
    assert cache_path.parent == tmp_path
    assert cache_path.name.startswith('.test.xml.')
    assert cache_path.name.endswith('.pp-terminal.db')

    # Extract checksum part
    name_parts = cache_path.name.split('.')
    # Format: .test.xml.<checksum>.pp-terminal.db
    # Split: ['', 'test', 'xml', '<checksum>', 'pp-terminal', 'db']
    assert len(name_parts) == 6
    checksum = name_parts[3]
    assert len(checksum) == 64  # SHA-256 hex digest

def test_cache_path_consistency(tmp_path: Path) -> None:
    """Test that same file produces same cache path."""
    xml_file = tmp_path / "test.xml"
    xml_file.write_text("<?xml version='1.0'?><test>data</test>")

    cache_path1 = get_cache_path(xml_file)
    cache_path2 = get_cache_path(xml_file)

    assert cache_path1 == cache_path2

def test_cache_path_changes_on_modification(tmp_path: Path) -> None:
    """Test that modified file produces different cache path."""
    xml_file = tmp_path / "test.xml"
    xml_file.write_text("<?xml version='1.0'?><test>data</test>")

    cache_path1 = get_cache_path(xml_file)

    # Modify file
    xml_file.write_text("<?xml version='1.0'?><test>modified</test>")

    cache_path2 = get_cache_path(xml_file)

    assert cache_path1 != cache_path2
    assert cache_path1.parent == cache_path2.parent

def test_cache_path_with_large_file(tmp_path: Path) -> None:
    """Test cache path generation for large file."""
    xml_file = tmp_path / "large.xml"
    # Write 100KB of data (> 8KB chunk size)
    large_content = "<?xml version='1.0'?><test>" + ("a" * 100000) + "</test>"
    xml_file.write_text(large_content)

    cache_path = get_cache_path(xml_file)

    assert cache_path.name.startswith('.large.xml.')
    assert cache_path.name.endswith('.pp-terminal.db')

def test_cache_path_missing_file(tmp_path: Path) -> None:
    """Test that missing file raises OSError."""
    missing_file = tmp_path / "missing.xml"

    with pytest.raises(OSError):
        get_cache_path(missing_file)
