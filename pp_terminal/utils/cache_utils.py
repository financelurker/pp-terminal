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

import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_FILE_SUFFIX = ".pp-terminal.db"


def _calculate_xml_checksum(xml_path: Path) -> str:
    """
    Calculate SHA-256 checksum of XML file.

    Reads file in binary chunks to handle large files efficiently.

    Args:
        xml_path: Path to XML file

    Returns:
        SHA-256 hex digest string (64 characters)

    Raises:
        OSError: If file cannot be read
    """
    sha256 = hashlib.sha256()
    with open(xml_path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_cache_path(xml_path: Path) -> Path:
    checksum = _calculate_xml_checksum(xml_path)

    return xml_path.parent / f".{xml_path.name}.{checksum}{_FILE_SUFFIX}"


def cleanup_old_cache_files(xml_path: Path) -> None:
    """
    Delete old cache files with different checksums.

    Searches for cache files matching pattern: <xml-filename>.pp-cache.*.db
    Deletes all except the one with current_checksum.

    Args:
        xml_path: Path to XML file
        current_checksum: Current checksum to preserve

    Raises:
        OSError: If cache files cannot be deleted (logged as warning, not raised)
    """
    cache_pattern = f".{xml_path.name}.*{_FILE_SUFFIX}"

    try:
        for cache_file in xml_path.parent.glob(cache_pattern):
            if cache_file.name != get_cache_path(xml_path).name:
                try:
                    cache_file.unlink()
                    log.debug('Deleted old cache file "%s"', cache_file)
                except FileNotFoundError:
                    # File already deleted (race condition), ignore
                    pass
                except OSError as e:
                    log.warning('Failed to delete old cache file "%s": %s', cache_file, str(e))
    except Exception as e:  # pylint: disable=broad-exception-caught
        log.warning('Failed to cleanup old cache files: %s', str(e))
