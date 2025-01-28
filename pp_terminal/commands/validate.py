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

from rich.console import Console
import pandas as pd
import typer

from ..df_filter import filter_by_date, filter_not_retired
from ..helper import run_all_group_cmds
from ..portfolio_service import PortfolioService

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)

validate_app = typer.Typer()
app.add_typer(validate_app, name="validate", help='Run a number of different validation checks on the portfolio data')


@validate_app.command(name="security-prices")
def validate_security_prices_uptodate(ctx: typer.Context) -> None:
    """
    Validate the timeliness of the security prices
    """

    portfolio = ctx.obj.portfolio  # type: PortfolioService

    latest_prices = portfolio.prices.groupby(['SecurityId']).tail(1)

    cutoff_date = datetime.now() - timedelta(weeks=4)  # @todo make configurable

    latest_prices = pd.merge(latest_prices, portfolio.securities, left_on='SecurityId', right_index=True, how='left')
    latest_prices = latest_prices.pipe(filter_by_date, target_date=cutoff_date).pipe(filter_not_retired)
    latest_prices = latest_prices.reset_index()[['Wkn', 'Name', 'Date']].to_dict(orient='records')

    for latest_price in latest_prices:
        log.warning('Latest price for security "%s" is from %s', latest_price['Name'], latest_price['Date'])


@validate_app.callback(invoke_without_command=True)
@run_all_group_cmds(validate_app)
def validate_all(ctx: typer.Context) -> None:  # pylint: disable=unused-argument
    return
