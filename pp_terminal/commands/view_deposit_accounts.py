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
from datetime import datetime

from rich.console import Console
import pandas as pd
import typer

from ..df_filter import filter_not_retired, unstack_column_by_currency
from ..helper import handle_nothing_found

from ..portfolio_service import PortfolioService
from ..portfolio_snapshot import PortfolioSnapshot
from ..table_decorator import TableDecorator

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def calculate_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    balances = (pd.merge(snapshot.portfolio.deposit_accounts, snapshot.balances, left_index=True, right_on='AccountId', how="right")
            .sort_values(by='Balance'))
    balances = balances.pipe(filter_not_retired)[['Name', 'Balance', 'currency']]  # pylint: disable=singleton-comparison

    balances = balances.pipe(unstack_column_by_currency, column='Balance')
    if snapshot.portfolio.base_currency in balances:
        balances.sort_values(by=snapshot.portfolio.base_currency, inplace=True)

    return balances


@app.command(name="deposit-accounts")
def print_accounts_table(ctx: typer.Context, by: datetime = datetime.now()) -> None:
    """
    Show a detailed table with the current balance per deposit account.
    """

    portfolio = ctx.obj.portfolio # type: PortfolioService

    df = calculate_sum(PortfolioSnapshot(portfolio, by))

    if df.empty:
        raise handle_nothing_found(console)

    table = TableDecorator(title="Balances on Deposit Accounts", caption=f"per {by.strftime("%Y-%m-%d")}", show_index=False)
    table.add_df(df)

    console.print()
    console.print(table)
    console.print()
