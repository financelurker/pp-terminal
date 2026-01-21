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

import pandas as pd
import typer

from ..df_filter import unstack_column_by_currency
from ..exceptions import InputError
from ..helper import footer
from ..output import OutputStrategy, Console
from ..portfolio import Portfolio
from ..portfolio_snapshot import PortfolioSnapshot
from ..schemas import AccountType
from ..table_decorator import TableOptions
from ..validation_engine import validate_accounts, ValidationResult

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def _normalize_columns(requested_columns: list[str], available_columns: list[str]) -> list[str]:
    """Normalize and validate column names (case-insensitive matching)."""
    normalized = []
    available_lower = {col.lower(): col for col in available_columns}

    for col in requested_columns:
        col_lower = col.strip().lower()
        if col_lower not in available_lower:
            raise InputError(f"Column '{col}' not found. Available columns: {', '.join(sorted(available_columns))}")
        normalized.append(available_lower[col_lower])

    return normalized


def calculate_deposit_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    balances = (pd.merge(snapshot.portfolio.deposit_accounts, snapshot.balances, left_index=True, right_on='account_id', how="right", validate='one_to_many')
            .sort_values(by='Balance'))

    return balances[balances['Balance'] >= 0.01][['Name', 'Type', 'Balance']]


def calculate_securities_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    values = (pd.merge(snapshot.portfolio.securities_accounts, snapshot.values.groupby(['account_id', 'currency']).sum(), left_index=True, right_on='account_id', how="right", validate='one_to_many')
            .sort_values(by='Balance'))

    return values[values['Balance'] >= 0.01][['Name', 'Type', 'Balance']]


@app.command(name="accounts")
def print_accounts(  # pylint: disable=too-many-locals
    ctx: typer.Context,
    type: AccountType | None = None,  # pylint: disable=redefined-builtin
    by: datetime = datetime.now(),
    columns: str | None = None
) -> None:
    """
    Show a detailed table with the current balance per deposit account.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy
    config = ctx.obj.config

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

    # Add validation messages column
    validation_results = validate_accounts(portfolio, snapshot, config)
    account_ids = df.index.get_level_values('account_id')
    df['Messages'] = account_ids.map(lambda aid: validation_results.get(str(aid), ValidationResult.empty()).messages)

    if columns is None:
        # Default: unstack Balance and show all columns with Messages at the end
        if 'Balance' in df.columns:
            df = df.pipe(unstack_column_by_currency, column='Balance', base_currency=snapshot.portfolio.base_currency)
        non_messages_cols = [col for col in df.columns if col != 'Messages']
        df = df[non_messages_cols + ['Messages']]
    else:
        requested_columns = [col.strip() for col in columns.split(',')]
        available_before_unstack = ['Name', 'Type', 'Balance', 'Messages']
        selected_columns_preunstack = _normalize_columns(requested_columns, available_before_unstack)

        if 'Balance' in selected_columns_preunstack and 'Balance' in df.columns:
            df = df.pipe(unstack_column_by_currency, column='Balance', base_currency=snapshot.portfolio.base_currency)

        # Map to actual columns after unstacking
        selected_columns = []
        for col in selected_columns_preunstack:
            if col == 'Balance':
                # Include all currency columns (columns that are not Name, Type, Messages)
                currency_cols = [c for c in df.columns if c not in ['Name', 'Type', 'Messages']]
                selected_columns.extend(currency_cols)
            elif col in df.columns:
                selected_columns.append(col)

        df = df[selected_columns]

    console.print(*output.result_table(
        df, TableOptions(title="Balances on Accounts", caption=f"in total {len(df)} entries, per {by.strftime("%Y-%m-%d")}", show_index=True)
    ))
    console.print(output.text(footer()), style="dim")
