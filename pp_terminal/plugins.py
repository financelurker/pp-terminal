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

import logging
import importlib.metadata
from importlib.metadata import EntryPoint

import typer
from typer.models import TyperInfo

log = logging.getLogger(__name__)


def load_command_plugins(app: typer.Typer) -> None:
    """
    Dynamically load external plugins and add them as subcommands.
    """

    # Discover plugins via entry points defined in pyproject.toml
    for entry_point in importlib.metadata.entry_points(group="pp_terminal.commands"):
        try:
            plugin = entry_point.load()
            if not isinstance(plugin, typer.Typer):
                raise RuntimeError('not a Typer app')

            group = _get_app_group_from_entry_point(app, entry_point)
            if group.typer_instance is None:
                raise RuntimeError('missing instance')

            group.typer_instance.add_typer(plugin)
            log.debug('loaded plugin command "%s" into group "%s"', entry_point.name, group.name)
        except Exception as e: # pylint: disable=broad-exception-caught
            log.error("failed to load plugin %s, ignoring: %s", entry_point.name, e)


def _get_app_group_from_entry_point(app: typer.Typer, entry_point: EntryPoint) -> TyperInfo:
    for group in app.registered_groups:
        if group.name == entry_point.name.split('.', 1)[0] and group.typer_instance is not None:
            return group

    return TyperInfo(app, name="")
