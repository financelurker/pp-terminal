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

import pandas as pd
import typer

from ..df_filter import unstack_column_by_currency
from ..exceptions import InputError
from ..output import OutputStrategy, Console
from ..portfolio import Portfolio
from ..portfolio_snapshot import PortfolioSnapshot
from ..schemas import AccountType
from ..table_decorator import TableOptions

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def calculate_deposit_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    balances = (pd.merge(snapshot.portfolio.deposit_accounts, snapshot.balances, left_index=True, right_on='account_id', how="right")
            .sort_values(by='Balance'))

    return balances[balances['Balance'] >= 0.01][['Name', 'Type', 'Balance']]


def calculate_securities_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    values = (pd.merge(snapshot.portfolio.securities_accounts, snapshot.values.groupby(['account_id', 'currency']).sum(), left_index=True, right_on='account_id', how="right")
            .sort_values(by='Balance'))

    return values[values['Balance'] >= 0.01][['Name', 'Type', 'Balance']]


@app.command(name="accounts")
def print_accounts(ctx: typer.Context, type: AccountType | None = None, by: datetime = datetime.now()) -> None:  # pylint: disable=redefined-builtin
    """
    Show a detailed table with the current balance per deposit account.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy

    snapshot = PortfolioSnapshot(portfolio, by)

    df1 = None
    if type == AccountType.DEPOSIT or type is None:
        df1 = calculate_deposit_accounts_sum(snapshot)

    df2 = None
    if type == AccountType.SECURITIES or type is None:
        df2 = calculate_securities_accounts_sum(snapshot)

    df = pd.concat([df1, df2]) if df1 is not None or df2 is not None else None

    if df is None:
        raise InputError('invalid account type')

    df = df.pipe(unstack_column_by_currency, column='Balance', base_currency=snapshot.portfolio.base_currency)

    console.print(*output.result_table(
        df, TableOptions(title="Balances on Accounts", caption=f"per {by.strftime("%Y-%m-%d")}", show_index=False)
    ))
