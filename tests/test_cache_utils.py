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

from pp_terminal.cache_utils import cleanup_old_cache_files, get_cache_path


class TestGetCachePath:
    """Tests for get_cache_path function."""

    def test_cache_path_format(self, tmp_path: Path) -> None:
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

    def test_cache_path_consistency(self, tmp_path: Path) -> None:
        """Test that same file produces same cache path."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        cache_path1 = get_cache_path(xml_file)
        cache_path2 = get_cache_path(xml_file)

        assert cache_path1 == cache_path2

    def test_cache_path_changes_on_modification(self, tmp_path: Path) -> None:
        """Test that modified file produces different cache path."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        cache_path1 = get_cache_path(xml_file)

        # Modify file
        xml_file.write_text("<?xml version='1.0'?><test>modified</test>")

        cache_path2 = get_cache_path(xml_file)

        assert cache_path1 != cache_path2
        assert cache_path1.parent == cache_path2.parent

    def test_cache_path_with_large_file(self, tmp_path: Path) -> None:
        """Test cache path generation for large file."""
        xml_file = tmp_path / "large.xml"
        # Write 100KB of data (> 8KB chunk size)
        large_content = "<?xml version='1.0'?><test>" + ("a" * 100000) + "</test>"
        xml_file.write_text(large_content)

        cache_path = get_cache_path(xml_file)

        assert cache_path.name.startswith('.large.xml.')
        assert cache_path.name.endswith('.pp-terminal.db')

    def test_cache_path_missing_file(self, tmp_path: Path) -> None:
        """Test that missing file raises OSError."""
        missing_file = tmp_path / "missing.xml"

        with pytest.raises(OSError):
            get_cache_path(missing_file)


class TestCleanupOldCacheFiles:
    """Tests for cleanup_old_cache_files function."""

    def test_cleanup_removes_old_cache_files(self, tmp_path: Path) -> None:
        """Test that old cache files are removed."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        # Get current cache path
        current_cache = get_cache_path(xml_file)

        # Create old cache files with different checksums
        old_cache1 = tmp_path / ".test.xml.abc123.pp-terminal.db"
        old_cache2 = tmp_path / ".test.xml.def456.pp-terminal.db"
        old_cache1.write_text("old cache")
        old_cache2.write_text("old cache")

        # Create current cache file
        current_cache.write_text("current cache")

        # Cleanup
        cleanup_old_cache_files(xml_file)

        # Verify old files deleted, current file preserved
        assert not old_cache1.exists()
        assert not old_cache2.exists()
        assert current_cache.exists()

    def test_cleanup_preserves_current_cache(self, tmp_path: Path) -> None:
        """Test that current cache file is not deleted."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        # Get and create current cache
        current_cache = get_cache_path(xml_file)
        current_cache.write_text("current cache")

        cleanup_old_cache_files(xml_file)

        assert current_cache.exists()
        assert current_cache.read_text() == "current cache"

    def test_cleanup_no_cache_files(self, tmp_path: Path) -> None:
        """Test cleanup when no cache files exist."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        # Should not raise exception
        cleanup_old_cache_files(xml_file)

    def test_cleanup_ignores_unrelated_files(self, tmp_path: Path) -> None:
        """Test that cleanup only targets cache files for this XML."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        # Create unrelated files
        other_file1 = tmp_path / "test.xml.backup"
        other_file2 = tmp_path / ".other.xml.abc123.pp-terminal.db"
        other_file1.write_text("backup")
        other_file2.write_text("other cache")

        cleanup_old_cache_files(xml_file)

        # Unrelated files should be preserved
        assert other_file1.exists()
        assert other_file2.exists()

    def test_cleanup_handles_already_deleted_file(self, tmp_path: Path) -> None:
        """Test that cleanup handles race condition when file is already deleted."""
        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<?xml version='1.0'?><test>data</test>")

        # Create an old cache file that we'll delete manually to simulate race condition
        old_cache = tmp_path / ".test.xml.abc123.pp-terminal.db"
        old_cache.write_text("old cache")

        # Delete the file before cleanup runs (simulating concurrent deletion)
        old_cache.unlink()

        # Should not raise exception
        cleanup_old_cache_files(xml_file)
