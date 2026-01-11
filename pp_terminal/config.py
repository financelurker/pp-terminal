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

import json
import logging
from pathlib import Path
from typing import Any, Dict, cast

from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError
from typer_config import conf_callback_factory
from typer_config.loaders import json_loader

log = logging.getLogger(__name__)

# Global storage for the loaded config
_loaded_config: Dict[str, Any] = {}


def _load_schema() -> dict[str, Any]:
    schema_path = Path(__file__).parent / 'config.schema.json'
    with open(schema_path, 'r', encoding='utf-8') as f:
        return cast(dict[str, Any], json.load(f))


def validated_json_loader(config_path: str) -> Dict[str, Any]:
    """
    Load and validate JSON configuration file for use with typer-config.

    This loader wraps typer-config's json_loader with JSON schema validation.

    Args:
        config_path: Path to the configuration file

    Returns:
        Validated configuration dictionary

    Raises:
        JsonSchemaValidationError: If config fails schema validation
    """
    global _loaded_config  # pylint: disable=global-statement

    if config_path == '':
        return _loaded_config

    config = json_loader(config_path)

    schema = _load_schema()
    validator = Draft7Validator(schema)

    errors = sorted(validator.iter_errors(config), key=lambda e: e.path)
    if errors:
        error_messages = []
        for error in errors:
            path = '.'.join(str(p) for p in error.path) if error.path else 'root'
            error_messages.append(f"  {path}: {error.message}")

        raise JsonSchemaValidationError(
            f"Config validation failed for {config_path}:\n" + '\n'.join(error_messages)
        )

    log.debug("Loaded and validated config from file \"%s\"", config_path)

    # Store config globally for access by commands
    _loaded_config = config

    return config


def get_config() -> Dict[str, Any]:
    """
    Get the currently loaded configuration.

    Returns:
        The loaded configuration dictionary, or empty dict if no config was loaded.
    """
    return _loaded_config


# Create the config callback for use with @use_config decorator
validated_config_callback = conf_callback_factory(validated_json_loader)
