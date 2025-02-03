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
from datetime import date
from typing import List, Any, Callable

import babel.numbers
import pandas as pd
import typer
from babel import Locale
from babel.numbers import format_currency
from typer.models import CommandFunctionType

from .schemas import Money

log = logging.getLogger(__name__)


def currency_exists(currency_code: str, locale: str | None = None) -> bool:
    return currency_code in Locale(str(locale)).currencies


def format_money(value: Money, currency: str = '', locale: str | None = babel.numbers.LC_NUMERIC) -> str:
    try:
        currency = currency if not pd.isna(currency) and currency_exists(currency, locale) else ''

        return format_currency(value, currency, locale=locale) if not pd.isna(value) and isinstance(value, Money) else ''
    except Exception:  # pylint: disable=broad-exception-caught
        # fallback e.g. if system locale is None/not set, or currency does not exist
        return f"{value:.2f}" if isinstance(value, Money) else ''


def enum_types_to_name(enum_list: List[Any]) -> List[Any]:
    # prepare for enum storage in dataframe
    for element in enum_list:
        element['Type'] = element['Type'].name

    return enum_list


def enum_list_to_values(enum_list: List[Any]) -> List[Any]:
    return [item.value for item in enum_list]


def run_all_group_cmds(app: typer.Typer) -> Callable[[CommandFunctionType], Callable[[typer.Context], CommandFunctionType]]:
    def decorator(func: CommandFunctionType) -> Callable[[typer.Context], CommandFunctionType]:
        def wrapper(ctx: typer.Context) -> Any:
            invoked_command = ctx.invoked_subcommand
            if ctx.invoked_subcommand is None:
                for command in app.registered_commands:
                    if command.callback is not None:
                        ctx.invoked_subcommand = command.name
                        log.debug('Running group command "%s"..', command.name)
                        command.callback(ctx)
            ctx.invoked_subcommand = invoked_command

            return func(ctx)
        return wrapper
    return decorator


def get_last_year() -> str:
    return str(date.today().year - 1)
