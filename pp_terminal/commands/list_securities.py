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

import typer

from ..exceptions import InputError
from ..helper import footer
from ..output import OutputStrategy, Console
from ..portfolio import Portfolio
from ..portfolio_snapshot import PortfolioSnapshot
from ..table_decorator import TableOptions
from ..validation_engine import validate_securities, ValidationResult

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


@app.command(name="securities")
def print_securities(  # pylint: disable=too-many-locals
    ctx: typer.Context,
    by: datetime = datetime.now(),
    active: bool = False,
    in_stock: bool = False,
    columns: str = 'ID,Name,Wkn,Currency,Shares,Messages'
) -> None:
    """
    Show a detailed table with all securities and their IDs.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy
    config = ctx.obj.config

    securities = portfolio.securities
    if securities is None:
        raise InputError("No securities found in portfolio")

    snapshot = PortfolioSnapshot(portfolio, by)
    shares = snapshot.shares

    attribute_map = config.get('attributes', {})

    # Reset index to make SecurityId a column and rename columns
    df = securities.reset_index().rename(columns={'uuid': 'SecurityId', 'currency': 'Currency', 'currencyCode': 'Currency'})

    if shares is not None and not shares.empty:
        shares_by_security = shares.groupby('SecurityId').sum()
        df = df.merge(shares_by_security, left_on='SecurityId', right_index=True, how='left', validate='one_to_one')
        df['Shares'] = df['Shares'].fillna(0.0)
    else:
        df['Shares'] = 0.0

    if active and 'is_retired' in df.columns:
        df = df[~df['is_retired']]

    if in_stock:
        df = df[df['Shares'] > 0.001]

    validation_results = validate_securities(portfolio, config)
    df['Messages'] = df['SecurityId'].map(
        lambda sid: validation_results.get(str(sid), ValidationResult.empty()).messages or ''
    )

    # Parse and normalize requested columns
    requested_columns = [col.strip() for col in columns.split(',')]
    available_columns = list(df.columns)

    # Allow "ID" as an alias for "SecurityId"
    available_with_alias = available_columns + ['ID']
    selected_columns = _normalize_columns(requested_columns, available_with_alias, attribute_map)

    # Map ID back to SecurityId for selection
    selected_columns = ['SecurityId' if col == 'ID' else col for col in selected_columns]

    # Filter to selected columns
    df = df[selected_columns]

    if 'SecurityId' in df.columns:
        df = df.rename(columns={'SecurityId': 'ID'})

    # Rename UUID columns to friendly names
    if attribute_map:
        uuid_to_name = {uuid: name for name, uuid in attribute_map.items()}
        rename_map = {col: uuid_to_name[col] for col in df.columns if col in uuid_to_name}
        if rename_map:
            df = df.rename(columns=rename_map)

    # Drop is_retired if it's still in the dataframe
    if 'is_retired' in df.columns and 'is_retired' not in columns:
        df = df.drop(columns=['is_retired'])

    df = df.sort_values(by='Name') if 'Name' in df.columns else df

    console.print(*output.result_table(
        df, TableOptions(
            title=f"{'Active ' if active else ''}Securities",
            caption=f"in total {len(df)} entries, per {by.strftime("%Y-%m-%d")}",
            show_index=False,
            show_total=False
        )
    ))
    console.print(output.text(footer()), style="dim")
