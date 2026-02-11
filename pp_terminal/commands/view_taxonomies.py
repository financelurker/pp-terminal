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

from typing import cast

import pandas as pd
import typer

from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.output.strategy import OutputStrategy, Console
from pp_terminal.output.table_decorator import TableOptions
from pp_terminal.utils.helper import footer

app = typer.Typer()
console = Console()


def prepare_taxonomies_df(portfolio: Portfolio) -> pd.DataFrame:
    assignments = portfolio.taxonomy_assignments
    if assignments.empty:
        return pd.DataFrame(columns=['Taxonomy', 'Category', 'Securities', 'Accounts'])

    counts = (assignments.groupby(['taxonomyName', 'categoryName', 'itemType'])
              .size()
              .unstack('itemType', fill_value=0)
              .rename(columns={'security': 'Securities', 'account': 'Accounts'})
              .reset_index()
              .rename(columns={'taxonomyName': 'Taxonomy', 'categoryName': 'Category'}))

    for col in ('Securities', 'Accounts'):
        if col not in counts.columns:
            counts[col] = 0

    return counts[['Taxonomy', 'Category', 'Securities', 'Accounts']].sort_values(['Taxonomy', 'Category'])


@app.command(name="taxonomies")
def print_taxonomies(ctx: typer.Context) -> None:
    """Show all taxonomies with their categories and assignment counts."""
    portfolio = cast(Portfolio, ctx.obj.portfolio)
    output = cast(OutputStrategy, ctx.obj.output)

    df = prepare_taxonomies_df(portfolio)

    console.print(*output.result_table(
        df, TableOptions(title="Taxonomies", caption=f"{len(df)} categories", show_index=False)
    ))
    console.print(output.text(footer()), style="dim")
