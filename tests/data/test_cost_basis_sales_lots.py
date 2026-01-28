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

from pp_terminal.data.cost_basis import match_sales_to_lots
from pp_terminal.data.tax import FifoLot
from pp_terminal.domain.schemas import AccountType, TransactionType


def test_partial_lot_consumption() -> None:
    """Test that sales partially consume lots in FIFO order."""
    lots: list[FifoLot] = [
        {
            'purchase_date': datetime(2020, 1, 15),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 100.0,
            'cost_basis': 1000.0,
            'capital_gain': 0.0
        },
        {
            'purchase_date': datetime(2020, 6, 20),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 150.0,
            'cost_basis': 1500.0,
            'capital_gain': 0.0
        }
    ]

    sales = pd.DataFrame([
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1400.0, 7.0, AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    remaining_lots = match_sales_to_lots(lots, sales)

    # Sale of 7 shares consumes 7 from first lot (10 shares), leaving 3 shares in first lot
    # Second lot (10 shares) remains untouched
    assert len(remaining_lots) == 2
    assert remaining_lots[0]['shares'] == pytest.approx(3.0, abs=0.0001)
    assert remaining_lots[0]['cost_basis'] == pytest.approx(300.0, abs=0.01)
    assert remaining_lots[1]['shares'] == pytest.approx(10.0, abs=0.0001)
    assert remaining_lots[1]['cost_basis'] == pytest.approx(1500.0, abs=0.01)

def test_full_lot_consumption() -> None:
    """Test that sales fully consume lots."""
    lots: list[FifoLot] = [
        {
            'purchase_date': datetime(2020, 1, 15),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 100.0,
            'cost_basis': 1000.0,
            'capital_gain': 0.0
        }
    ]

    sales = pd.DataFrame([
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 2000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    remaining_lots = match_sales_to_lots(lots, sales)

    assert len(remaining_lots) == 0

def test_multiple_sales_fifo_order() -> None:
    """Test that multiple sales consume lots in FIFO order."""
    lots: list[FifoLot] = [
        {
            'purchase_date': datetime(2020, 1, 15),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 100.0,
            'cost_basis': 1000.0,
            'capital_gain': 0.0
        },
        {
            'purchase_date': datetime(2020, 6, 20),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 150.0,
            'cost_basis': 1500.0,
            'capital_gain': 0.0
        },
        {
            'purchase_date': datetime(2022, 1, 5),
            'account_id': 'acc-1',
            'shares': 20.0,
            'purchase_price': 100.0,
            'cost_basis': 2000.0,
            'capital_gain': 0.0
        }
    ]

    sales = pd.DataFrame([
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1400.0, 7.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Consume 7 from lot 1
        [datetime(2023, 6, 15), 'acc-1', 'sec-1', TransactionType.SELL.value, 1800.0, 12.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Consume 3 from lot 1, 9 from lot 2
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    remaining_lots = match_sales_to_lots(lots, sales)

    # Lot 1 (10 shares): 7 sold in first sale, 3 sold in second sale -> fully consumed
    # Lot 2 (10 shares): 9 sold in second sale -> 1 share remaining
    # Lot 3 (20 shares): untouched
    assert len(remaining_lots) == 2
    assert remaining_lots[0]['shares'] == pytest.approx(1.0, abs=0.0001)
    assert remaining_lots[1]['shares'] == pytest.approx(20.0, abs=0.0001)

def test_no_sales() -> None:
    """Test with no sales (all lots remain)."""
    lots: list[FifoLot] = [
        {
            'purchase_date': datetime(2020, 1, 15),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 100.0,
            'cost_basis': 1000.0,
            'capital_gain': 0.0
        }
    ]

    sales = pd.DataFrame(columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    remaining_lots = match_sales_to_lots(lots, sales)

    assert len(remaining_lots) == 1
    assert remaining_lots[0]['shares'] == 10.0

def test_delivery_outbound_included() -> None:
    """Test that DELIVERY_OUTBOUND transactions are included in sales."""
    lots: list[FifoLot] = [
        {
            'purchase_date': datetime(2020, 1, 15),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 100.0,
            'cost_basis': 1000.0,
            'capital_gain': 0.0
        }
    ]

    sales = pd.DataFrame([
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.DELIVERY_OUTBOUND.value, 0.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    remaining_lots = match_sales_to_lots(lots, sales)

    assert len(remaining_lots) == 1
    assert remaining_lots[0]['shares'] == pytest.approx(5.0, abs=0.0001)

def test_lots_not_mutated() -> None:
    """Test that original lots are not mutated (deep copy)."""
    lots: list[FifoLot] = [
        {
            'purchase_date': datetime(2020, 1, 15),
            'account_id': 'acc-1',
            'shares': 10.0,
            'purchase_price': 100.0,
            'cost_basis': 1000.0,
            'capital_gain': 0.0
        }
    ]

    sales = pd.DataFrame([
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1000.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    original_shares = lots[0]['shares']
    match_sales_to_lots(lots, sales)

    assert lots[0]['shares'] == original_shares  # Original not mutated
