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

import pandas as pd
import typer
from typer.models import CommandFunctionType

from ..df_filter import filter_not_retired
from ..exceptions import ValidationError
from ..helper import run_all_group_cmds
from ..output import Console
from ..portfolio_snapshot import PortfolioSnapshot
from .validation_rules import create_rule, get_applicable_rule

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

    rules_config = config.get('validation', {}).get('securities', {}).get('rules', [])

    if not rules_config:
        log.debug('No security validation rules configured')
        return

    if portfolio.securities is None or portfolio.securities.empty:
        log.debug('No securities found in portfolio')
        return

    rules = [create_rule(rule_config) for rule_config in rules_config]

    latest_prices = portfolio.prices.groupby(['SecurityId']).tail(1)

    securities_with_prices = pd.merge(
        portfolio.securities,
        latest_prices.reset_index()[['SecurityId', 'date', 'Price']],
        left_index=True,
        right_on='SecurityId',
        how='left',
        validate='one_to_one'
    ).set_index('SecurityId')

    securities_with_prices = securities_with_prices.pipe(filter_not_retired)

    if securities_with_prices.empty:
        log.debug('No non-retired securities found')
        return

    has_errors = False
    for security_id, security in securities_with_prices.iterrows():
        rule = get_applicable_rule(security_id, security, rules)
        if rule is None:
            continue

        context = {
            'latest_price_date': security.get('date') if pd.notna(security.get('date')) else None,
            'current_price': security.get('Price') if pd.notna(security.get('Price')) else None,
            'portfolio': portfolio,
        }

        if rule.validate(security, security_id, context):
            has_errors = True

    if has_errors:
        raise ValidationError()


@validate_app.command(name="accounts")
@catch_errors
def validate_accounts(ctx: typer.Context) -> None:
    """Validate deposit accounts using configured validation rules."""
    portfolio = ctx.obj.portfolio
    config = ctx.obj.config

    rules_config = config.get('validation', {}).get('accounts', {}).get('rules', [])

    if not rules_config:
        log.debug('No account validation rules configured')
        return

    snapshot = PortfolioSnapshot(portfolio, datetime.now())
    if snapshot.balances is None or snapshot.balances.empty:
        log.debug('No deposit account balances found')
        return

    if portfolio.deposit_accounts is None:
        log.debug('No deposit accounts found in portfolio')
        return

    rules = [create_rule(rule_config) for rule_config in rules_config]

    total_balances = snapshot.balances.groupby('account_id').sum()
    total_balances.name = 'TotalBalance'

    accounts_with_balances = pd.merge(
        portfolio.deposit_accounts,
        total_balances,
        left_index=True,
        right_index=True,
        how='right',
        validate='one_to_one'
    )

    accounts_with_balances = accounts_with_balances.pipe(filter_not_retired)

    if accounts_with_balances.empty:
        log.debug('No non-retired accounts found')
        return

    has_errors = False
    for account_id, account in accounts_with_balances.iterrows():
        rule = get_applicable_rule(account_id, account, rules)
        if rule is None:
            continue

        context = {
            'balance': account['TotalBalance'],
            'portfolio': portfolio,
            'snapshot': snapshot,
        }

        if rule.validate(account, account_id, context):
            has_errors = True

    if has_errors:
        raise ValidationError()


@validate_app.callback(invoke_without_command=True)
@run_all_group_cmds(validate_app)
def validate_all(ctx: typer.Context) -> None:  # pylint: disable=unused-argument
    if ctx.invoked_subcommand is None:
        raise typer.Exit(exit_code)
