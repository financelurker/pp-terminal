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

import locale
from abc import abstractmethod, ABC
from enum import Enum
from typing import Any

import pandas as pd
import rich
from rich.console import NewLine

from pp_terminal.schemas import Money
from pp_terminal.table_decorator import TableDecorator


class OutputFormat(str, Enum):
    TABLE = 'table'
    CSV = 'csv'
    JSON = 'json'


class Console(rich.console.Console):
    def print(self, *objects: Any, **kwargs: Any) -> None:
        kwargs['end'] = ''  # no newline at the end by default
        super().print(*objects, **kwargs)


class OutputStrategy(ABC):
    @abstractmethod
    def result_table(self, df: pd.DataFrame | None, title: str = '', caption: str = '', show_index: bool = False, footer_lines: int = 0) -> Any:
        pass

    def hint(self, message: str) -> str:  # pylint: disable=unused-argument
        return ''

    def empty_result(self) -> str:
        return ''


class RichOutputStrategy(OutputStrategy):
    def result_table(self, df: pd.DataFrame | None, title: str = '', caption: str = '', show_index: bool = False, footer_lines: int = 0) -> Any:
        if df is None or df.empty:
            return self.empty_result()

        table = TableDecorator(title=title, caption=caption, show_index=show_index, money_formatter=format_money)
        table.add_df(df)

        return NewLine(), table

    def hint(self, message: str) -> str:
        return ':bulb: [bold]Hint:[/bold] ' + message + "\n"

    def empty_result(self) -> str:
        return 'Nothing here..:sleeping: '


class CsvOutputStrategy(OutputStrategy):
    def result_table(self, df: pd.DataFrame | None, title: str = '', caption: str = '', show_index: bool = False, footer_lines: int = 0) -> Any:
        if df is None:
            return self.empty_result()

        return (df.to_csv(index=show_index, float_format='%.2f'), )


class JsonOutputStrategy(OutputStrategy):
    def result_table(self, df: pd.DataFrame | None, title: str = '', caption: str = '', show_index: bool = False, footer_lines: int = 0) -> Any:
        if df is None:
            return self.empty_result()

        return (df.to_json(index=show_index, orient='records'), )


def create_strategy(output_format: OutputFormat) -> OutputStrategy:
    if output_format == OutputFormat.TABLE:
        return RichOutputStrategy()

    if output_format == OutputFormat.CSV:
        return CsvOutputStrategy()

    if output_format == OutputFormat.JSON:
        return JsonOutputStrategy()

    raise NotImplementedError('output format "' + output_format + '" not supported yet')


def format_money(value: Money) -> str:
    return locale.format_string("EUR %.2f", value, grouping=True, monetary=True) if not pd.isna(value) and isinstance(value, Money) else ''
