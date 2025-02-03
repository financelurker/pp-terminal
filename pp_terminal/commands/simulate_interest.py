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
from typing import Annotated, Any

import numpy as np
import pandas as pd
import typer
from rich.console import Console

from pp_terminal.df_filter import filter_later_than, filter_by_type
from pp_terminal.helper import get_last_year
from pp_terminal.output import OutputStrategy
from pp_terminal.portfolio import Portfolio
from pp_terminal.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.schemas import Percent, TransactionType, Money
from pp_terminal.table_decorator import TableOptions, format_value

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


_DAYS_PER_YEAR = 360


def calculate_interest(snapshot_begin: PortfolioSnapshot, snapshot_end: PortfolioSnapshot, interest_rate: Percent) -> pd.DataFrame | None:
    transactions = snapshot_end.deposit_account_transactions
    if transactions is None:
        return None

    df = transactions.reset_index(level='date').sort_values(by=['account_id', 'currency', 'date'])
    df = df.groupby(['account_id', 'currency', 'date']).agg({'date': 'min', 'amount': 'sum'})

    df['days_diff'] = df.groupby(['account_id', 'currency'])['date'].diff().dt.days.fillna(0).astype(int)
    df['balance'] = df.groupby(['account_id', 'currency'])['amount'].cumsum()
    df['weighted_balance'] = df['balance'] * df['days_diff']
    df['interest_rate'] = np.power(1 + interest_rate / _DAYS_PER_YEAR, df['days_diff']) - 1
    df['interest'] = df['balance'] * df['interest_rate']

    df = df.pipe(filter_later_than, target_date=snapshot_begin.date)
    df = df.groupby(['account_id', 'currency']).agg({'interest': 'sum', 'weighted_balance': 'sum', 'days_diff': 'sum'})
    df['mean_balance'] = (df['weighted_balance'] / df['days_diff']).fillna(0)

    interest_transactions = (transactions.pipe(filter_by_type, transaction_types=[TransactionType.INTEREST, TransactionType.INTEREST_CHARGE])
                             .pipe(filter_later_than, target_date=snapshot_begin.date)
                             .reset_index(level='date'))
    interest_transactions['amount'] = interest_transactions['amount'] + interest_transactions['taxes']
    df['actual_interest'] = interest_transactions.groupby(['account_id', 'currency'])['amount'].sum().fillna(0)

    interest_per_account = (pd.merge(snapshot_end.portfolio.deposit_accounts, df, left_index=True, right_on='account_id', how="right")
                .sort_values(by='interest'))

    return interest_per_account[interest_per_account['interest'] > 0][['Name', 'currency', 'mean_balance', 'interest', 'actual_interest']]


def _format_value_wrapper(value: Any, index: str, row: pd.Series) -> str:
    if index == 'Actual Interest' and isinstance(value, Money):
        color = 'red' if value < row['Simulated Interest'] else 'green'
        return f"[{color}]{format_value(value, index, row)}[/{color}]"

    return format_value(value, index, row)


@app.command(name="interest")
def simulate_interest_rate(
        ctx: typer.Context,
        interest_rate: Annotated[Percent, typer.Option(min=0, max=100, prompt="Interest Rate (%)", prompt_required=True)],
        year: Annotated[datetime, typer.Option(formats=["%Y"], help="The year to calculate the preliminary tax for", prompt=True, default_factory=get_last_year)],
) -> None:
    """
    Simulate a given interest rate for a deposit account.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(year.year, 1, 1))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(year.year, 12, 31))

    df = calculate_interest(snapshot_begin, snapshot_end, interest_rate)
    if df is not None:
        df = df.rename(columns={'mean_balance': '⌀ Balance', 'interest': 'Simulated Interest', 'actual_interest': 'Actual Interest'})
        df.insert(3, 'Interest Rate', f"{interest_rate * 100}%")

    console.print(*output.result_table(
        df, TableOptions(title='Simulated Interest on Accounts', caption=f"for {year.strftime("%Y")}, excl. taxes", show_index=False, show_total=False, value_formatter=_format_value_wrapper)
    ))
