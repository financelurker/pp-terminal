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

from typing import Any, cast


def _get_attribute_mapping(config: dict[str, Any]) -> dict[str, str]:
    """
    Extract friendly attribute name to UUID mapping from config.

    Returns:
        Dictionary mapping friendly names to UUIDs from both accounts and securities
    """
    attributes = config.get('attributes', {})

    accounts = cast(dict[str, str], attributes.get('accounts', {}))
    securities = cast(dict[str, str], attributes.get('securities', {}))

    return accounts | securities


def get_attribute_id_by_name(config: dict[str, Any], friendly_name: str) -> str | None:
    return _get_attribute_mapping(config).get(friendly_name)
