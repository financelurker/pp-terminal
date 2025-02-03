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

from abc import abstractmethod, ABC
from enum import Enum
from typing import Any

import pandas as pd
import rich
from rich.console import NewLine

from .table_decorator import TableDecorator, TableOptions


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
    def result_table(self, df: pd.DataFrame | None, options: TableOptions) -> Any:
        pass

    def hint(self, message: str) -> str:  # pylint: disable=unused-argument
        return ''

    def warning(self, message: str) -> str:  # pylint: disable=unused-argument
        return ''

    def empty_result(self) -> str:
        return ''


class RichOutputStrategy(OutputStrategy):
    def result_table(self, df: pd.DataFrame | None, options: TableOptions) -> Any:
        if df is None or df.empty:
            return self.empty_result(), NewLine()

        table = TableDecorator(options)
        table.add_df(df)

        return NewLine(), table, NewLine()

    def hint(self, message: str) -> str:
        return ':bulb: [bold]Hint:[/bold] ' + message + "\n"

    def warning(self, message: str) -> str:
        return ':backhand_index_pointing_right: [bold]Warning:[/bold] ' + message + "\n"

    def empty_result(self) -> str:
        return 'Nothing here..:sleeping: '


class CsvOutputStrategy(OutputStrategy):
    def result_table(self, df: pd.DataFrame | None, options: TableOptions) -> Any:
        if df is None:
            return self.empty_result()

        return (df.to_csv(index=options.show_index, float_format='%.2f'), )


class JsonOutputStrategy(OutputStrategy):
    def result_table(self, df: pd.DataFrame | None, options: TableOptions) -> Any:
        if df is None:
            return self.empty_result()

        return (df.to_json(index=options.show_index, orient='records'), )


def create_strategy(output_format: OutputFormat) -> OutputStrategy:
    match output_format:
        case OutputFormat.TABLE:
            return RichOutputStrategy()
        case OutputFormat.CSV:
            return CsvOutputStrategy()
        case OutputFormat.JSON:
            return JsonOutputStrategy()

    raise NotImplementedError('output format "' + output_format + '" not supported yet')
