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

from datetime import datetime

import pandas as pd
import pytest
from pandera.typing import DataFrame

from pp_terminal.data.tax import calculate_prepaid_tax_per_lot
from pp_terminal.domain.schemas import PurchaseTransactionSchema, TransactionType, AccountType


def test_single_year_full_year(tax_csv_data: pd.DataFrame) -> None:
    """Test tax credit for single lot held full year."""
    df = DataFrame[PurchaseTransactionSchema]([
        [TransactionType.SELL.value, AccountType.SECURITIES.value, 100.0, 10000.0]
    ], columns=['type', 'accountType', 'shares', 'amount'],
        index=pd.MultiIndex.from_arrays([[datetime(2020, 1, 1)], ['acc-1'], ['sec-1']], names=['date', 'accountId', 'securityId']))

    # Current date 2022-12-31: years held = 2020, 2021 (not 2022 because last_year = current_year - 1)
    current_date = datetime(2022, 12, 31)
    tax = float(calculate_prepaid_tax_per_lot(df, current_date, tax_csv_data).sum())

    # 2020: 100 shares * €0.05 = €5.00 (full year)
    # 2021: 100 shares * €0.06 = €6.00 (full year)
    # Total: €11.00
    assert tax == pytest.approx(11.0, abs=0.01)

def test_purchase_year_month_proration(tax_csv_data: pd.DataFrame) -> None:
    """Test that purchase year is prorated by months held."""
    df = DataFrame[PurchaseTransactionSchema]([
        [TransactionType.BUY.value, AccountType.SECURITIES.value, 100.0, 10000.0]
    ], columns=['type', 'accountType', 'shares', 'amount'],
        index=pd.MultiIndex.from_arrays([[datetime(2020, 6, 15)], ['acc-1'], ['sec-1']], names=['date', 'accountId', 'securityId']))

    current_date = datetime(2022, 12, 31)
    credit = float(calculate_prepaid_tax_per_lot(df, current_date, tax_csv_data).sum())

    # 2020: 100 shares * €0.05 * (13-6)/12 = 100 * 0.05 * 7/12 = €2.92
    # 2021: 100 shares * €0.06 * 1.0 = €6.00
    # Total: €8.92
    assert credit == pytest.approx(8.92, abs=0.01)

def test_multiple_lots_different_accounts(tax_csv_data: pd.DataFrame) -> None:
    """Test tax credit across multiple lots in different accounts."""
    df = DataFrame[PurchaseTransactionSchema]([
        [TransactionType.BUY.value, AccountType.SECURITIES.value, 50.0, 5000.0],
        [TransactionType.BUY.value, AccountType.SECURITIES.value, 30.0, 3600.0],
    ], columns=['type', 'accountType', 'shares', 'amount'],
        index=pd.MultiIndex.from_arrays(
            [[datetime(2020, 1, 1), datetime(2021, 1, 1)], ['acc-1', 'acc-2'], ['sec-1', 'sec-1']],
            names=['date', 'accountId', 'securityId']))

    current_date = datetime(2022, 12, 31)
    credit = float(calculate_prepaid_tax_per_lot(df, current_date, tax_csv_data).sum())

    # Lot 1 (acc-1):
    #   2020: 50 * €0.05 = €2.50
    #   2021: 50 * €0.06 = €3.00
    # Lot 2 (acc-2):
    #   2021: 30 * €0.06 = €1.80
    # Total: €7.30
    assert credit == pytest.approx(7.30, abs=0.01)

def test_purchased_in_current_year_no_credit(tax_csv_data: pd.DataFrame) -> None:
    """Test that lots purchased in current year have no tax credit."""
    df = DataFrame[PurchaseTransactionSchema]([
        [TransactionType.BUY.value, AccountType.SECURITIES.value, 100.0, 10000.0]
    ], columns=['type', 'accountType', 'shares', 'amount'],
        index=pd.MultiIndex.from_arrays([[datetime(2022, 6, 1)], ['acc-1'], ['sec-1']], names=['date', 'accountId', 'securityId']))

    current_date = datetime(2022, 12, 31)
    credit = float(calculate_prepaid_tax_per_lot(df, current_date, tax_csv_data).sum())

    # Purchased in 2022, evaluated in 2022 -> last_year = 2021 < first_year = 2022
    assert credit == 0.0

def test_missing_tax_data_ignored(tax_csv_data: pd.DataFrame) -> None:
    """Test that missing tax data for year/account/security is ignored (returns 0)."""
    df = DataFrame[PurchaseTransactionSchema]([
        [TransactionType.BUY.value, AccountType.SECURITIES.value, 100.0, 10000.0]
    ], columns=['type', 'accountType', 'shares', 'amount'],
        index=pd.MultiIndex.from_arrays([[datetime(2019, 1, 1)], ['acc-1'], ['sec-1']], names=['date', 'accountId', 'securityId']))

    current_date = datetime(2022, 12, 31)
    credit = float(calculate_prepaid_tax_per_lot(df, current_date, tax_csv_data).sum())

    # 2019: No data in CSV -> €0.00
    # 2020: 100 * €0.05 = €5.00
    # 2021: 100 * €0.06 = €6.00
    # Total: €11.00 (2019 silently ignored)
    assert credit == pytest.approx(11.0, abs=0.01)

def test_no_tax_csv_returns_zero() -> None:
    """Test that None tax CSV returns zero credit."""
    df = DataFrame[PurchaseTransactionSchema]([
        [TransactionType.BUY.value, AccountType.SECURITIES.value, 100.0, 10000.0]
    ], columns=['type', 'accountType', 'shares', 'amount'],
        index=pd.MultiIndex.from_arrays([[datetime(2020, 1, 1)], ['acc-1'], ['sec-1']], names=['date', 'accountId', 'securityId']))

    current_date = datetime(2022, 12, 31)
    credit = float(calculate_prepaid_tax_per_lot(df, current_date, None).sum())

    assert credit == 0.0
