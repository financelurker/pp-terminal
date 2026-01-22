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

from ..column_utils import normalize_columns, rename_uuid_columns
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
    selected_columns = normalize_columns(requested_columns, available_with_alias, attribute_map)

    # Map ID back to SecurityId for selection
    selected_columns = ['SecurityId' if col == 'ID' else col for col in selected_columns]

    # Filter to selected columns
    df = df[selected_columns]

    if 'SecurityId' in df.columns:
        df = df.rename(columns={'SecurityId': 'ID'})

    df = rename_uuid_columns(df, attribute_map)

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
