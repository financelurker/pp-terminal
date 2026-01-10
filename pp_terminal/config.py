"""
    Copyright (C) 2025 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

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

import json
import logging
from pathlib import Path
from typing import Optional

from jsonschema import Draft7Validator

from .exceptions import ValidationError

log = logging.getLogger(__name__)


def _load_schema() -> dict:
    schema_path = Path(__file__).parent.parent / 'config.schema.json'
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_config(config_path: Optional[Path] = None) -> dict:
    """
    Load and validate configuration file.

    Args:
        config_path: Explicit path to config file. If None, looks for ./.pp-terminal.json

    Returns:
        Validated configuration dictionary

    Raises:
        ValidationError: If config file is invalid or fails schema validation
    """
    if config_path is None:
        config_path = Path('.pp-terminal.json')
        if not config_path.exists():
            return {}

    if not config_path.exists():
        raise ValidationError(f"Config file not found: {config_path}")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid JSON in config file {config_path}: {e}") from e

    schema = _load_schema()
    validator = Draft7Validator(schema)

    errors = sorted(validator.iter_errors(config), key=lambda e: e.path)
    if errors:
        error_messages = []
        for error in errors:
            path = '.'.join(str(p) for p in error.path) if error.path else 'root'
            error_messages.append(f"  {path}: {error.message}")

        raise ValidationError(
            f"Config validation failed for {config_path}:\n" + '\n'.join(error_messages)
        )

    log.debug("Loaded config from file \"%s\"", config_path)

    return config
