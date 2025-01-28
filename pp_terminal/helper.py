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
from typing import List, Any, Callable

import pandas as pd
from rich.console import Console
import typer
from babel.numbers import format_currency
from typer.models import CommandFunctionType


from pp_terminal.schemas import Money

log = logging.getLogger(__name__)


def format_money(value: float, currency: str = '') -> str:
    return format_currency(value, currency) if not pd.isna(value) and isinstance(value, Money) else ''


def print_hint(console: Console, message: str) -> None:
    console.print(':bulb: [bold]Hint:[/bold] ' + message)
    console.print()


def print_warning(console: Console, message: str) -> None:
    console.print(':backhand_index_pointing_right: [bold]Warning:[/bold] ' + message)
    console.print()


def handle_nothing_found(console: Console) -> Exception:
    console.print('Nothing here..:sleeping: ')

    return typer.Exit()


def enum_types_to_name(enum_list: List[Any]) -> List[Any]:
    # prepare for enum storage in dataframe
    for element in enum_list:
        element['Type'] = element['Type'].name

    return enum_list


def enum_list_to_values(enum_list: List[Any]) -> List[Any]:
    return [item.value for item in enum_list]


def run_all_group_cmds(app: typer.Typer) -> Callable[[CommandFunctionType], Callable[[typer.Context], CommandFunctionType]]:
    def decorator(func: CommandFunctionType) -> Callable[[typer.Context], CommandFunctionType]:
        def wrapper(ctx: typer.Context) -> CommandFunctionType:
            if ctx.invoked_subcommand is None:
                for command in app.registered_commands:
                    if command.callback is not None:
                        log.debug('Running group command "%s"..', command.name)
                        command.callback(ctx)

            return func
        return wrapper
    return decorator
