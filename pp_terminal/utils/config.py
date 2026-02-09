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
import os
from pathlib import Path
from typing import Any, Dict, cast

from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError
from typer_config import conf_callback_factory
from typer_config.loaders import toml_loader

log = logging.getLogger(__name__)
type Config = Dict[str, Any]

# Global storage for the loaded config
_loaded_config: Config = {}


def get_tax_rate(config: Config) -> float:
    return float(config.get('tax', {}).get('rate', 26.375))


def get_exempt_rate(config: Config) -> float:
    return float(config.get('tax', {}).get('exemption-rate', 30.0))


def get_exempt_rate_attribute(config: Config) -> str | None:
    value = config.get('tax', {}).get('exemption-rate-attribute')
    return str(value) if value is not None else None


def get_tax_files(config: Config) -> list[Path]:
    tax_config = config.get('tax', {})

    if 'files' in tax_config:
        files = tax_config['files']
        if isinstance(files, list):
            return [Path(f) for f in files]
        return [Path(files)]

    return []



def _load_schema() -> dict[str, Any]:
    schema_path = Path(__file__).parent.parent / 'config.schema.json'
    with open(schema_path, 'r', encoding='utf-8') as f:
        return cast(dict[str, Any], json.load(f))


def validated_toml_loader(config_path: str) -> Config:
    """
    Load and validate TOML configuration file for use with typer-config.

    This loader wraps typer-config's toml_loader with JSON schema validation.
    """
    global _loaded_config  # pylint: disable=global-statement

    if config_path == '':
        config_path = os.environ.get('PP_TERMINAL_CONFIG', '')

    if config_path == '':
        return _loaded_config

    config = toml_loader(config_path)

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

    # Presence-based anonymization: if 'anonymize' is a dict (config section exists),
    # convert to boolean True for typer-config CLI mapping while keeping the full config in _loaded_config
    if isinstance(config.get('anonymize'), dict):
        config = {**config, 'anonymize': True}

    return config


def get_config() -> Config:
    """
    Get the currently loaded configuration - should only be used with prior @use_config(validated_config_callback).

    Returns:
        The loaded configuration dictionary, or empty dict if no config was loaded.
    """
    return _loaded_config


def get_command_config(config: Config, path: str, default: Any = None) -> Any:
    """
    Retrieve command-specific configuration from nested path.

    Args:
        config: Configuration dictionary
        path: Dot-separated path (e.g., 'view.accounts.fields')
        default: Default value if path doesn't exist

    Returns:
        Configuration value at path, or default if not found
    """
    keys = ['commands'] + path.split('.')
    value: Any = config

    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
            if value is None:
                return default
        else:
            return default

    return value if value is not None else default


# Create the config callback for use with @use_config decorator
validated_config_callback = conf_callback_factory(validated_toml_loader)
