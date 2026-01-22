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


def _normalize_columns(requested_columns: list[str], available_columns: list[str], attribute_map: dict[str, str] | None = None) -> list[str]:
    """
    Normalize and validate column names (case-insensitive matching).

    Args:
        requested_columns: List of column names requested by user
        available_columns: List of actual column names in the dataframe
        attribute_map: Optional mapping of friendly attribute names to UUID column names
    """
    normalized = []
    available_lower = {col.lower(): col for col in available_columns}

    # Create reverse mapping for attribute names (friendly name -> UUID)
    attr_name_to_uuid = {}
    if attribute_map:
        for friendly_name, uuid in attribute_map.items():
            attr_name_to_uuid[friendly_name.lower()] = uuid

    for col in requested_columns:
        col_lower = col.strip().lower()

        # Try direct column match first
        if col_lower in available_lower:
            normalized.append(available_lower[col_lower])
        # Try attribute name mapping
        elif col_lower in attr_name_to_uuid:
            uuid_col = attr_name_to_uuid[col_lower]
            if uuid_col in available_columns:
                normalized.append(uuid_col)
            else:
                raise InputError(f"Attribute '{col}' (UUID: {uuid_col}) not found in data")
        else:
            # Build helpful error message including attribute names
            # Filter out internal columns (starting with _) and UUID columns
            uuid_values = set(attribute_map.values()) if attribute_map else set()
            available_names = sorted([
                col for col in available_columns
                if not col.startswith('_') and col not in uuid_values
            ])
            if attribute_map:
                available_names.extend(f"{name} (attribute)" for name in sorted(attribute_map.keys()))
            raise InputError(f"Column '{col}' not found. Available columns: {', '.join(available_names)}")

    return normalized


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
    columns: str = 'ID,Name,Type,Balance,Messages'
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

    # Available columns before unstacking - need to account for ID which will be from the index
    available_before_unstack = list(set(df.columns) - {'Balance'}) + ['ID']
    if 'Balance' in df.columns:
        available_before_unstack.append('Balance')

    selected_columns_preunstack = _normalize_columns(requested_columns, available_before_unstack, attribute_map)

    # Unstack Balance if requested (before resetting index)
    if 'Balance' in selected_columns_preunstack and 'Balance' in df.columns:
        # Track columns before unstacking
        cols_before_unstack = set(df.columns)

        df = df.pipe(unstack_column_by_currency, column='Balance', base_currency=snapshot.portfolio.base_currency)

        # Identify currency columns (added by unstacking)
        cols_after_unstack = set(df.columns)
        currency_cols = list(cols_after_unstack - cols_before_unstack)

        # After unstacking, reset index to make account_id a regular column
        df = df.reset_index()
        df = df.rename(columns={'account_id': 'ID'})

        # Map to actual columns after unstacking and index reset
        selected_columns = []
        for col in selected_columns_preunstack:
            if col == 'Balance':
                # Include only the currency columns created by unstacking
                selected_columns.extend(currency_cols)
            elif col in df.columns:
                selected_columns.append(col)

        df = df[selected_columns]

        # Rename UUID columns to friendly names
        if attribute_map:
            uuid_to_name = {uuid: name for name, uuid in attribute_map.items()}
            rename_map = {col: uuid_to_name[col] for col in df.columns if col in uuid_to_name}
            if rename_map:
                df = df.rename(columns=rename_map)

        # Set ID as index for display
        if 'ID' in df.columns:
            df = df.set_index('ID')
    else:
        # Balance not requested, drop the currency column first (exists as both column and index level)
        if 'currency' in df.columns:
            df = df.drop(columns=['currency'])

        # Now reset the MultiIndex and rename
        df = df.reset_index()
        df = df.rename(columns={'account_id': 'ID'})

        # Drop currency again if it came from the index
        if 'currency' in df.columns:
            df = df.drop(columns=['currency'])

        # Filter to selected columns
        selected_columns = [col for col in selected_columns_preunstack if col in df.columns]
        df = df[selected_columns]

        # Rename UUID columns to friendly names
        if attribute_map:
            uuid_to_name = {uuid: name for name, uuid in attribute_map.items()}
            rename_map = {col: uuid_to_name[col] for col in df.columns if col in uuid_to_name}
            if rename_map:
                df = df.rename(columns=rename_map)

        # Set ID as index for display
        if 'ID' in df.columns:
            df = df.set_index('ID')

    console.print(*output.result_table(
        df, TableOptions(title="Balances on Accounts", caption=f"in total {len(df)} entries, per {by.strftime("%Y-%m-%d")}", show_index=True)
    ))
    console.print(output.text(footer()), style="dim")
