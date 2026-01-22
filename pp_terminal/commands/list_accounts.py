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

from ..column_utils import normalize_columns, rename_uuid_columns
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


def _prepare_df_for_display(
    df: pd.DataFrame,
    selected_columns_preunstack: list[str],
    snapshot: PortfolioSnapshot,
    attribute_map: dict[str, str] | None,
    unstack_balance: bool
) -> pd.DataFrame:
    """Prepare DataFrame for display with optional Balance unstacking."""
    if unstack_balance:
        cols_before_unstack = set(df.columns)
        df = df.pipe(unstack_column_by_currency, column='Balance', base_currency=snapshot.portfolio.base_currency)
        currency_cols = list(set(df.columns) - cols_before_unstack)
    else:
        if 'currency' in df.columns:
            df = df.drop(columns=['currency'])
        currency_cols = []

    df = df.reset_index()
    df = df.rename(columns={'account_id': 'AccountId'})

    if 'currency' in df.columns:
        df = df.drop(columns=['currency'])

    selected_columns = []
    for col in selected_columns_preunstack:
        if col == 'Balance' and currency_cols:
            selected_columns.extend(currency_cols)
        elif col in df.columns:
            selected_columns.append(col)

    df = df[selected_columns]
    df = rename_uuid_columns(df, attribute_map)

    if 'AccountId' in df.columns:
        df = df.set_index('AccountId')

    return df


def calculate_deposit_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    balances = (pd.merge(snapshot.portfolio.deposit_accounts, snapshot.balances, left_index=True, right_on='account_id', how="right", validate='one_to_many')
            .sort_values(by='Balance'))

    balances = balances[balances['Balance'] >= 0.01]
    # Drop columns that are not useful for display
    cols_to_drop = [col for col in balances.columns if col in ['Referenceaccount_id', 'is_retired']]
    if cols_to_drop:
        balances = balances.drop(columns=cols_to_drop)
    return balances


def calculate_securities_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    values = (pd.merge(snapshot.portfolio.securities_accounts, snapshot.values.groupby(['account_id', 'currency']).sum(), left_index=True, right_on='account_id', how="right", validate='one_to_many')
            .sort_values(by='Balance'))

    values = values[values['Balance'] >= 0.01]
    # Drop columns that are not useful for display
    cols_to_drop = [col for col in values.columns if col in ['Referenceaccount_id', 'is_retired']]
    if cols_to_drop:
        values = values.drop(columns=cols_to_drop)
    return values


@app.command(name="accounts")
def print_accounts(  # pylint: disable=too-many-locals
    ctx: typer.Context,
    type: AccountType | None = None,  # pylint: disable=redefined-builtin
    by: datetime = datetime.now(),
    columns: str = 'AccountId,Name,Type,Balance,Messages'
) -> None:
    """
    Show a detailed table with the current balance per deposit account.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy
    config = ctx.obj.config

    attribute_map = config.get('attributes', {})

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
    df['Messages'] = account_ids.map(
        lambda aid: validation_results.get(str(aid), ValidationResult.empty()).messages or ''
    )

    # Parse requested columns
    requested_columns = [col.strip() for col in columns.split(',')]

    # Available columns before unstacking - need to account for AccountId which will be from the index
    available_before_unstack = list(set(df.columns) - {'Balance'}) + ['AccountId']
    if 'Balance' in df.columns:
        available_before_unstack.append('Balance')

    selected_columns_preunstack = normalize_columns(requested_columns, available_before_unstack, attribute_map)

    df = _prepare_df_for_display(
        df, selected_columns_preunstack, snapshot, attribute_map,
        unstack_balance='Balance' in selected_columns_preunstack and 'Balance' in df.columns
    )

    console.print(*output.result_table(
        df, TableOptions(title="Balances on Accounts", caption=f"in total {len(df)} entries, per {by.strftime("%Y-%m-%d")}", show_index=True)
    ))
    console.print(output.text(footer()), style="dim")
