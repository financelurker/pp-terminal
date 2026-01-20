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

import logging
from datetime import datetime
from functools import wraps
from typing import Callable, Any

import typer
from typer.models import CommandFunctionType

from ..exceptions import ValidationError
from ..helper import run_all_group_cmds
from ..output import Console
from ..portfolio_snapshot import PortfolioSnapshot
from ..validation_engine import validate_accounts as validate_accounts_engine
from ..validation_engine import validate_securities as validate_securities_engine

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
def validate_security_prices(ctx: typer.Context) -> None:
    """Validate the timeliness of security prices."""
    portfolio = ctx.obj.portfolio
    config = ctx.obj.config

    results = validate_securities_engine(portfolio, config)

    if not results:
        log.debug('No security validation rules configured or no securities to validate')
        return

    has_errors = False
    for result in results.values():
        if result.has_errors:
            has_errors = True

    if has_errors:
        raise ValidationError()


@validate_app.command(name="accounts")
@catch_errors
def validate_accounts(ctx: typer.Context) -> None:
    """Validate deposit accounts using configured validation rules."""
    portfolio = ctx.obj.portfolio
    config = ctx.obj.config

    snapshot = PortfolioSnapshot(portfolio, datetime.now())
    results = validate_accounts_engine(portfolio, snapshot, config)

    if not results:
        log.debug('No account validation rules configured or no accounts to validate')
        return

    has_errors = False
    for result in results.values():
        if result.has_errors:
            has_errors = True

    if has_errors:
        raise ValidationError()


@validate_app.callback(invoke_without_command=True)
@run_all_group_cmds(validate_app)
def validate_all(ctx: typer.Context) -> None:  # pylint: disable=unused-argument
    if ctx.invoked_subcommand is None:
        raise typer.Exit(exit_code)
