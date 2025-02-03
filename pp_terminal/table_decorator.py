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

from typing import Literal, Callable, Any

import pandas as pd
from rich.table import Table
from rich.text import Text

from .df_filter import drop_empty_values
from .helper import format_money
from .schemas import Money


def format_value(value: Any, index: str, row: pd.Series) -> str:
    return format_money(float(value), row['currency'] if 'currency' in row else index) if isinstance(value, Money) else str(value)


class TableOptions:  # pylint: disable=too-few-public-methods
    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
            self,
            title: str = '',
            caption: str = '',
            show_index: bool = True,
            show_total: bool = True,
            footer_lines: int = 0,
            value_formatter: Callable[[Any, str, pd.Series], str] = format_value
    ) -> None:
        self.title = title
        self.caption = caption
        self.show_index = show_index
        self.show_total = show_total
        self.footer_lines = footer_lines
        self.value_formatter = value_formatter


class TableDecorator(Table):
    _options: TableOptions

    def __init__(self, options: TableOptions) -> None:
        self._options = options

        super().__init__(show_footer=self.show_default_footer, title=options.title, caption=options.caption)

    @property
    def show_default_footer(self) -> bool:
        return self._options.show_total and self._options.footer_lines == 0  # multiple footer lines are not supported in rich by default

    def add_df(self, df: pd.DataFrame) -> Table:
        df = df.pipe(drop_empty_values)
        if df.empty:
            return self

        summary_row = (df.iloc[:-self._options.footer_lines] if self._options.footer_lines > 0 else df).select_dtypes(include='number').sum()  # only sum up numeric values
        if 'currency' in df:
            summary_row['currency'] = df['currency'].mode()[0]
        summary_row = pd.concat([summary_row, pd.Series(['Total'], index=['Name'])])

        # in case we have multiple footer lines, insert the total value into the right position in the dataframe
        df_bottom = None
        if self._options.show_total and not self.show_default_footer:
            df_bottom = df.iloc[-self._options.footer_lines:, :]
            df = df.iloc[:-self._options.footer_lines, :]
            df_bottom = pd.concat([df, summary_row.to_frame().T, df_bottom], ignore_index=True)

        # add DataFrame columns to the table
        for i, column in enumerate(df.columns):
            if str(column) == 'currency':
                continue

            footer_value = self._options.value_formatter(summary_row[column], str(column), summary_row) if self._options.show_total and column in summary_row.index else ''
            justify = 'right' if footer_value != '' else 'left'  # type: Literal["right", "left"]

            if not self._options.show_index and footer_value == '' and i == 0:  # column is non-numeric
                footer_value = 'Total'

            column_title = str(column)
            column_title = column_title[0].upper() + column_title[1:]

            self.add_column(column_title, footer=footer_value if self.show_default_footer else '', justify=justify)

        for row_data in self._prepare_rows(df):
            self.add_row(*row_data)

        if df_bottom is None:
            return self

        self._print_footer(df_bottom)

        return self

    def _print_footer(self, df: pd.DataFrame) -> None:
        self.add_section()

        i = 0
        for row_data in self._prepare_rows(df.iloc[-(self._options.footer_lines + 1):]):
            self.add_row(*list(map(lambda x: Text(x, style='bold') if i == 0 else x, row_data)))  # pylint: disable=cell-var-from-loop
            i += 1

    def _prepare_rows(self, df: pd.DataFrame) -> list[list[str]]:
        rows = []
        for index, row in df.iterrows():
            row_data = [str(index)] if self._options.show_index else []
            row_data.extend([self._options.value_formatter(value, str(index), row) for index, value in row.drop('currency', errors='ignore').items()])
            rows.append(row_data)

        return rows
