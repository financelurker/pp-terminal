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

import typer

from ..output import OutputStrategy, Console
from ..portfolio import Portfolio
from ..table_decorator import TableOptions

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


@app.command(name="securities")
def print_securities(ctx: typer.Context) -> None:
    """
    Show a detailed table with all securities and their IDs.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy

    securities = portfolio.securities
    assert securities is not None

    df = securities.reset_index()[['uuid', 'Name', 'Wkn', 'currency']].rename(columns={'uuid': 'SecurityId', 'currency': 'Currency'}).sort_values(by='Name')

    console.print(*output.result_table(
        df, TableOptions(title="Securities", show_index=False, show_total=False)
    ))
