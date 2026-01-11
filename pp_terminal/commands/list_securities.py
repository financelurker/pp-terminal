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

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


@app.command(name="securities")
def print_securities(ctx: typer.Context, by: datetime = datetime.now(), active: bool = False, in_stock: bool = False) -> None:
    """
    Show a detailed table with all securities and their IDs.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy

    securities = portfolio.securities
    if securities is None:
        raise InputError("No securities found in portfolio")

    snapshot = PortfolioSnapshot(portfolio, by)
    shares = snapshot.shares

    columns_to_select = ['uuid', 'Name', 'Wkn', 'currency']
    if 'is_retired' in securities.columns:
        columns_to_select.append('is_retired')

    df = securities.reset_index()[columns_to_select].rename(columns={'uuid': 'SecurityId', 'currency': 'Currency'})

    if shares is not None and not shares.empty:
        shares_by_security = shares.groupby('SecurityId').sum()
        df = df.merge(shares_by_security, left_on='SecurityId', right_index=True, how='left')
        df['Shares'] = df['Shares'].fillna(0.0)
    else:
        df['Shares'] = 0.0

    if active and 'is_retired' in df.columns:
        df = df[~df['is_retired']]

    if in_stock:
        df = df[df['Shares'] > 0.001]

    if 'is_retired' in df.columns:
        df = df.drop(columns=['is_retired'])

    df = df.sort_values(by='Name')

    console.print(*output.result_table(
        df, TableOptions(
            title="Securities",
            caption=f"in total {len(df)} entries, per {by.strftime("%Y-%m-%d")}",
            show_index=False,
            show_total=False
        )
    ))
    console.print(output.text(footer()), style="dim")
