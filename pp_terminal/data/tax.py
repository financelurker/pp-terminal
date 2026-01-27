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
from pandera.typing import DataFrame

from pp_terminal.exceptions import InputError
from pp_terminal.output.strategy import Console
from pp_terminal.domain.schemas import TaxPaidSchema

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def load_paid_taxes_from_csv(csv_path: Path) -> DataFrame[TaxPaidSchema]:
    """
    Load paid tax data from CSV (e.g. "Vorabpauschale").
    Expected format: date;account_id;security_id;tax_per_share
    """
    log.debug('Loading paid tax data from "%s"', csv_path)

    try:
        df = pd.read_csv(csv_path, sep=';', parse_dates=['date'])
    except FileNotFoundError as e:
        raise InputError(f"Paid tax data CSV file not found: {csv_path}") from e
    except Exception as e:
        raise InputError(f"Failed to read paid tax data CSV: {e}") from e

    required_columns = {'date', 'account_id', 'security_id', 'tax_per_share'}
    if not required_columns.issubset(df.columns):
        raise InputError(f"CSV missing required columns. Expected: {required_columns}, Got: {set(df.columns)}")

    # Extract year from date and create multi-index
    df['year'] = df['date'].dt.year
    df = df.set_index(['year', 'account_id', 'security_id'])

    TaxPaidSchema.validate(df)

    return cast(DataFrame[TaxPaidSchema], df[['tax_per_share']])
