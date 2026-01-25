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

from pp_terminal.output.column_utils import normalize_columns
from pp_terminal.exceptions import InputError
from pp_terminal.utils.helper import footer
from pp_terminal.output.strategy import OutputStrategy, Console
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.output.table_decorator import TableOptions
from pp_terminal.validation.engine import validate_securities, ValidationResult
from pp_terminal.utils.config import get_command_config

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


@app.command(name="securities")
def print_securities(  # pylint: disable=too-many-locals
    ctx: typer.Context,
    by: datetime = datetime.now(),
    active: bool = False,
    in_stock: bool = False,
    columns: str | None = None
) -> None:
    """
    Show a detailed table with all securities and their IDs.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy
    config = ctx.obj.config

    if columns is None:
        config_columns = get_command_config(config, 'view.securities.columns')
        if config_columns:
            columns = ','.join(config_columns)
        else:
            columns = 'SecurityId,Name,Wkn,Currency,Shares,Messages'

    securities = portfolio.securities
    if securities is None:
        raise InputError("No securities found in portfolio")

    snapshot = PortfolioSnapshot(portfolio, by)
    shares = snapshot.shares

    # Reset index to make SecurityId a column and rename columns
    df = securities.reset_index()

    if shares is not None and not shares.empty:
        shares_by_security = shares.groupby('securityId').sum()
        df = df.merge(shares_by_security, left_on='securityId', right_index=True, how='left', validate='one_to_one')
        df['shares'] = df['shares'].fillna(0.0)
    else:
        df['shares'] = 0.0

    if active and 'isRetired' in df.columns:
        df = df[~df['isRetired']]

    if in_stock:
        df = df[df['shares'] > 0.001]

    validation_results = validate_securities(portfolio, config)
    df['Messages'] = df['securityId'].map(
        lambda sid: validation_results.get(str(sid), ValidationResult.empty()).messages or ''
    )

    requested_columns = [col.strip() for col in columns.split(',')]
    selected_columns = normalize_columns(requested_columns, list(df.columns), portfolio.security_attributes)

    df = df[selected_columns]
    df = df.rename(columns=portfolio.security_attributes)

    if 'isRetired' in df.columns and 'isRetired' not in columns:
        df = df.drop(columns=['isRetired'])

    df = df.sort_values(by='name') if 'name' in df.columns else df

    console.print(*output.result_table(
        df, TableOptions(
            title=f"{'Active ' if active else ''}Securities",
            caption=f"{len(df)} entries per {by.strftime("%Y-%m-%d")}",
            show_index=False,
            show_total=False
        )
    ))
    console.print(output.text(footer()), style="dim")
