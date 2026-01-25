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

from pp_terminal.output.column_utils import normalize_columns
from pp_terminal.data.filters import unstack_column_by_currency
from pp_terminal.exceptions import InputError
from pp_terminal.utils.helper import footer
from pp_terminal.output.strategy import OutputStrategy, Console
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.schemas import AccountType
from pp_terminal.output.table_decorator import TableOptions
from pp_terminal.validation.engine import validate_accounts, ValidationResult
from pp_terminal.utils.config import get_command_config

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def _prepare_df_for_display(
    df: pd.DataFrame,
    selected_columns_preunstack: list[str],
    snapshot: PortfolioSnapshot,
    unstack_balance: bool
) -> pd.DataFrame:
    """Prepare DataFrame for display with optional balance unstacking."""
    if unstack_balance:
        cols_before_unstack = set(df.columns)
        df = df.pipe(unstack_column_by_currency, column='balance', base_currency=snapshot.portfolio.base_currency)
        currency_cols = list(set(df.columns) - cols_before_unstack)
    else:
        currency_cols = []

    # Drop currency column before reset_index if it exists (to avoid collision with index level)
    if 'currency' in df.columns:
        df = df.drop(columns=['currency'])

    df = df.reset_index()

    selected_columns = []
    for col in selected_columns_preunstack:
        if col == 'balance' and currency_cols:
            selected_columns.extend(currency_cols)
        elif col in df.columns:
            selected_columns.append(col)

    df = df[selected_columns]
    df = df.rename(columns=snapshot.portfolio.account_attributes)

    if 'accountId' in df.columns:
        df = df.set_index('accountId')

    return df


def calculate_deposit_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    balances = (pd.merge(snapshot.portfolio.deposit_accounts, snapshot.balances, left_index=True, right_on='accountId', how="right", validate='one_to_many')
            .sort_values(by='balance'))

    balances = balances[balances['balance'] >= 0.01]
    # Drop columns that are not useful for display
    cols_to_drop = [col for col in balances.columns if col in ['referenceAccount', 'isRetired']]
    if cols_to_drop:
        balances = balances.drop(columns=cols_to_drop)
    return balances


def calculate_securities_accounts_sum(snapshot: PortfolioSnapshot) -> pd.DataFrame:
    values = (pd.merge(snapshot.portfolio.securities_accounts, snapshot.values.groupby(['accountId', 'currency']).sum(), left_index=True, right_on='accountId', how="right", validate='one_to_many')
            .sort_values(by='balance'))

    values = values[values['balance'] >= 0.01]
    # Drop columns that are not useful for display
    cols_to_drop = [col for col in values.columns if col in ['referenceAccount', 'isRetired']]
    if cols_to_drop:
        values = values.drop(columns=cols_to_drop)
    return values


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

    if columns is None:
        config_columns = get_command_config(config, 'view.accounts.columns')
        if config_columns:
            columns = ','.join(config_columns)
        else:
            columns = 'AccountId,Name,Type,Balance,Messages'

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
    account_ids = df.index.get_level_values('accountId')
    df['Messages'] = account_ids.map(
        lambda aid: validation_results.get(str(aid), ValidationResult.empty()).messages or ''
    )

    requested_columns = [col.strip() for col in columns.split(',')]

    # Available columns before unstacking - need to account for accountId which will be from the index
    available_before_unstack = list(set(df.columns) - {'balance'}) + ['accountId']
    if 'balance' in df.columns:
        available_before_unstack.append('balance')

    selected_columns_preunstack = normalize_columns(requested_columns, available_before_unstack, portfolio.account_attributes)

    df = _prepare_df_for_display(
        df, selected_columns_preunstack, snapshot,
        unstack_balance='balance' in selected_columns_preunstack and 'balance' in df.columns
    )

    console.print(*output.result_table(
        df, TableOptions(title="Balances on Accounts", caption=f"{len(df)} entries per {by.strftime("%Y-%m-%d")}", show_index=True)
    ))
    console.print(output.text(footer()), style="dim")
