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
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Any

import pandas as pd
import typer
from typer.models import CommandFunctionType

from ..df_filter import filter_earlier_than, filter_not_retired
from ..exceptions import ValidationError
from ..helper import run_all_group_cmds
from ..output import Console
from ..portfolio import Portfolio

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)

validate_app = typer.Typer()
app.add_typer(validate_app, name="validate", help='Run a number of different validation checks on the portfolio data')


exit_code = 0  # pylint: disable=invalid-name


def catch_errors(func: CommandFunctionType) -> Callable[..., CommandFunctionType]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        global exit_code  # pylint: disable=global-statement

        try:
            return func(*args, **kwargs)
        except ValidationError:
            exit_code = 1
            ctx = kwargs['ctx'] if 'ctx' in kwargs else args[0] if len(args) > 0 else None

            if ctx and ctx.invoked_subcommand is None:
                raise typer.Exit(exit_code)  # pylint: disable=raise-missing-from

            return None

    return wrapper


@validate_app.command(name="security-prices")
@catch_errors
def validate_security_prices_uptodate(ctx: typer.Context, warning_after_days: int = 30, error_after_days: int = 90) -> None:
    """
    Validate the timeliness of the security prices
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio

    latest_prices = portfolio.prices.groupby(['SecurityId']).tail(1)

    warning_cutoff_date = datetime.now() - timedelta(days=warning_after_days)
    error_cutoff_date = datetime.now() - timedelta(days=error_after_days)

    latest_prices = pd.merge(latest_prices, portfolio.securities, left_on='SecurityId', right_index=True, how='left')
    latest_prices = latest_prices.pipe(filter_earlier_than, target_date=warning_cutoff_date).pipe(filter_not_retired)
    latest_prices = latest_prices.reset_index()[['Wkn', 'Name', 'date']].to_dict(orient='records')

    has_errors = False
    for latest_price in latest_prices:
        log_level = logging.WARNING
        if latest_price['date'] < error_cutoff_date:
            log_level = logging.ERROR
            has_errors = True

        log.log(log_level, 'Latest price for security "%s" is from %s', latest_price['Name'], latest_price['date'])

    if has_errors:
        raise ValidationError


@validate_app.callback(invoke_without_command=True)
@run_all_group_cmds(validate_app)
def validate_all(ctx: typer.Context) -> None:  # pylint: disable=unused-argument
    if ctx.invoked_subcommand is None:
        raise typer.Exit(exit_code)
