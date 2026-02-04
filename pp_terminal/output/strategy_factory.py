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

from pp_terminal.output.strategy import OutputFormat, OutputStrategy, RichOutputStrategy, CsvOutputStrategy, \
    JsonOutputStrategy
from pp_terminal.output.strategy_excel import ExcelOutputStrategy


def create_strategy(output_format: OutputFormat) -> OutputStrategy:
    match output_format:
        case OutputFormat.TABLE:
            return RichOutputStrategy()
        case OutputFormat.CSV:
            return CsvOutputStrategy()
        case OutputFormat.JSON:
            return JsonOutputStrategy()
        case OutputFormat.EXCEL:
            return ExcelOutputStrategy()

    raise NotImplementedError('output format "' + output_format + '" not supported yet')
