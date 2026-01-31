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
from pp_terminal.domain.schemas import TaxPaidSchema, Percent, Money, FifoLotSchema

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


def calculate_prepaid_tax_per_lot(
    lots: DataFrame[FifoLotSchema],
    current_date: datetime,
    tax_csv_data: DataFrame[TaxPaidSchema] | None
) -> pd.Series:
    """
    Calculate prepaid tax per lot (e.g. Vorabpauschale).

    Args:
        lots: Current FIFO lots DataFrame (after matching sales)
        current_date: Evaluation date (for year range calculation)
        tax_csv_data: CSV data with taxes paid per share, indexed by (year, account_id, security_id)

    Returns:
        Series of prepaid tax amounts, indexed to match the input lots dataframe.
    """
    if lots.empty or tax_csv_data is None or tax_csv_data.empty:
        return pd.Series(0.0, index=lots.index)

    # Add year columns and lot index to track original lot
    lots_with_years = lots.copy().reset_index()
    lots_with_years['lot_index'] = lots_with_years.index
    lots_with_years['first_year'] = lots_with_years['date'].dt.year
    lots_with_years['last_year'] = current_date.year - 1

    # Filter out current year purchases (no prepaid tax yet)
    lots_with_years = lots_with_years[lots_with_years['last_year'] >= lots_with_years['first_year']]

    if lots_with_years.empty:
        return pd.Series(0.0, index=lots.index)

    # Create year range for each lot
    lots_with_years['year_range'] = lots_with_years.apply(
        lambda row: list(range(row['first_year'], row['last_year'] + 1)),
        axis=1
    )

    # Explode into lot-year pairs
    lot_years = lots_with_years.explode('year_range').rename(columns={'year_range': 'year'})

    # Calculate month_factor (prorate for purchase year)
    lot_years['month_factor'] = 1.0
    is_first_year = lot_years['year'] == lot_years['first_year']
    lot_years.loc[is_first_year, 'month_factor'] = (
        (13 - lot_years.loc[is_first_year, 'date'].dt.month) / 12.0
    )

    tax_csv_data = tax_csv_data.reset_index().rename(columns={'account_id': 'accountId', 'security_id': 'securityId'})  # @todo
    lot_years = lot_years.merge(
        tax_csv_data,
        on=['year', 'accountId', 'securityId'],
        how='inner'
    )

    if lot_years.empty:
        return pd.Series(0.0, index=lots.index)

    if 'tax_free_allowance' not in lot_years.columns:
        lot_years['tax_free_allowance'] = 0.0
    else:
        lot_years['tax_free_allowance'] = lot_years['tax_free_allowance'].fillna(0.0)

    lot_years['taxes'] = (
        lot_years['shares'] * lot_years['tax_per_share'] * lot_years['month_factor'] - lot_years['tax_free_allowance']
    )

    # Group by lot_index to get per-lot totals
    per_lot_tax = lot_years.groupby('lot_index')['taxes'].sum()

    # Reindex to match original lots dataframe, filling missing with 0
    return per_lot_tax.reindex(lots.index, fill_value=0.0)
