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
from pathlib import Path
from typing import cast

import pandas as pd
import typer
from pandera.errors import SchemaError
from pandera.typing import DataFrame

from pp_terminal.exceptions import InputError
from pp_terminal.output.strategy import Console
from pp_terminal.domain.schemas import TaxPaidSchema, Percent

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def load_prepaid_tax_data_from_csv(csv_path: Path, tax_rate: Percent) -> DataFrame[TaxPaidSchema]:
    """
    Load paid tax data from CSV (e.g. "Vorabpauschale").
    """
    log.debug('Loading paid tax data from "%s"', csv_path)

    try:
        df = pd.read_csv(csv_path, sep=';', parse_dates=['date'])
    except FileNotFoundError as e:
        raise InputError(f"Prepaid tax data CSV file not found: {csv_path}") from e
    except Exception as e:
        raise InputError(f"Failed to read prepaid tax data CSV: {e}") from e

    df['year'] = df['date'].dt.year
    df['tax_per_share'] = df['deemed_income_base_per_share'] * tax_rate
    df = df.set_index(['year', 'account_id', 'security_id'])

    try:
        TaxPaidSchema.validate(df)
    except SchemaError as e:
        raise InputError(f"Prepaid tax data CSV is missing required columns: {e}") from e

    return cast(DataFrame[TaxPaidSchema], df[['tax_per_share', 'tax_free_allowance']])
