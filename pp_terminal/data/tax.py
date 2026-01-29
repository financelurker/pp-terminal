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
from pathlib import Path
from typing import TypedDict

import pandas as pd
import typer
from pandera.errors import SchemaError
from pandera.typing import DataFrame

from pp_terminal.exceptions import InputError
from pp_terminal.output.strategy import Console
from pp_terminal.domain.schemas import TaxPaidSchema, Percent, Money

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


class FifoLot(TypedDict):
    purchase_date: datetime
    account_id: str
    shares: float
    purchase_price: Money
    cost_basis: Money
    capital_gain: Money


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
        return TaxPaidSchema.validate(df[['tax_per_share', 'tax_free_allowance']])
    except SchemaError as e:
        raise InputError(f"Prepaid tax data CSV is missing required columns: {e}") from e


def calculate_prepaid_tax_for_lots(
    lots: list[FifoLot],
    security_id: str,
    current_date: datetime,
    tax_csv_data: DataFrame[TaxPaidSchema] | None
) -> Money:
    """
    Calculate total prepaid tax on current lots (e.g. Vorabpauschale).

    Args:
        lots: Current FIFO lots (after matching sales)
        security_id: Security identifier for tax CSV lookup
        current_date: Evaluation date (for year range calculation)
        tax_csv_data: CSV data with taxes paid per share, indexed by (year, account_id, security_id)

    Returns:
        Total prepaid tax to reduce cost basis.
    """
    if tax_csv_data is None or tax_csv_data.empty:
        return 0.0

    total_tax = 0.0

    for lot in lots:
        first_year = lot['purchase_date'].year
        last_year = current_date.year - 1

        if last_year < first_year:
            # Purchased in current year - no prepaid tax yet
            continue

        # Calculate tax for each year
        for year in range(first_year, last_year + 1):
            try:
                tax_per_share = tax_csv_data.loc[(year, lot['account_id'], security_id), 'tax_per_share']
            except KeyError:
                continue

            try:
                tax_free_allowance_per_year = tax_csv_data.loc[(year, lot['account_id'], security_id), 'tax_free_allowance']
            except KeyError:
                # tax_free_allowance is optional
                tax_free_allowance_per_year = 0.0

            # For purchase year, prorate by months held
            if year == first_year:
                # Months held = 13 - purchase_month (e.g., June = month 6 -> 13-6 = 7 months)
                months_held = 13 - lot['purchase_date'].month
                month_factor = months_held / 12.0
            else:
                # Full year
                month_factor = 1.0

            total_tax += lot['shares'] * float(tax_per_share) * month_factor - float(tax_free_allowance_per_year)

    return total_tax
