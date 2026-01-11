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
# pylint: disable=duplicate-code

from datetime import datetime

import pandas as pd
import pytest

from pp_terminal.commands.simulate_share_sell import _calculate_fifo_lots, _calculate_taxes
from pp_terminal.exceptions import InputError
from pp_terminal.portfolio import Portfolio
from pp_terminal.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.schemas import AccountType, TransactionType


@pytest.fixture(name='share_sell_portfolio')
def provide_share_sell_portfolio() -> Portfolio:
    """Portfolio with multiple purchases for FIFO testing."""

    # Accounts
    accounts = pd.DataFrame([
        ['Depot1', AccountType.SECURITIES.value, 'account1', False, 'EUR'],
        ['Konto1', AccountType.DEPOSIT.value, None, False, 'EUR'],
    ], columns=['Name', 'Type', 'Referenceaccount_id', 'is_retired', 'currency'],
    index=['depot1', 'account1'])
    accounts.index.name = 'account_id'

    # Securities
    securities = pd.DataFrame([
        ['Test ETF', 'IE00B4L5Y983', 'EUR'],
    ], columns=['Name', 'Wkn', 'currency'], index=['sec1'])
    securities.index.name = 'SecurityId'

    # Transactions - Three purchases at different prices
    transactions = pd.DataFrame([
        [datetime(2022, 1, 15), 'depot1', 'sec1', TransactionType.BUY.value, 5000.0, 50.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # €100/share
        [datetime(2023, 6, 10), 'depot1', 'sec1', TransactionType.BUY.value, 7000.0, 50.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # €140/share
        [datetime(2024, 3, 20), 'depot1', 'sec1', TransactionType.BUY.value, 9000.0, 60.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # €150/share
    ], columns=['date', 'account_id', 'SecurityId', 'Type', 'amount', 'Shares', 'account_type', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'account_id', 'SecurityId'])

    # Prices
    prices = pd.DataFrame([
        [datetime(2024, 12, 31), 'sec1', 160.0],
    ], columns=['date', 'SecurityId', 'Price'])
    prices = prices.set_index(['date', 'SecurityId'])

    portfolio = Portfolio(accounts, transactions, securities, prices)
    portfolio.base_currency = 'EUR'
    return portfolio


def test_fifo_lots_single_purchase(share_sell_portfolio: Portfolio) -> None:
    """Test FIFO when selling shares from a single purchase."""
    snapshot = PortfolioSnapshot(share_sell_portfolio, datetime(2024, 12, 31))

    lots = _calculate_fifo_lots(snapshot, 'depot1', 'sec1', 30.0, 160.0)

    assert len(lots) == 1
    assert lots[0]['shares'] == 30.0
    assert lots[0]['purchase_price'] == 100.0
    assert lots[0]['cost_basis'] == 3000.0
    assert lots[0]['capital_gain'] == 1800.0  # 30 * (160 - 100)


def test_fifo_lots_multiple_purchases(share_sell_portfolio: Portfolio) -> None:
    """Test FIFO when selling shares across multiple purchases."""
    snapshot = PortfolioSnapshot(share_sell_portfolio, datetime(2024, 12, 31))

    # Sell 120 shares: 50 from first purchase, 50 from second, 20 from third
    lots = _calculate_fifo_lots(snapshot, 'depot1', 'sec1', 120.0, 160.0)

    assert len(lots) == 3

    # First lot: 50 shares @ €100
    assert lots[0]['shares'] == 50.0
    assert lots[0]['purchase_price'] == 100.0
    assert lots[0]['cost_basis'] == 5000.0
    assert lots[0]['capital_gain'] == 3000.0  # 50 * (160 - 100)

    # Second lot: 50 shares @ €140
    assert lots[1]['shares'] == 50.0
    assert lots[1]['purchase_price'] == 140.0
    assert lots[1]['cost_basis'] == 7000.0
    assert lots[1]['capital_gain'] == 1000.0  # 50 * (160 - 140)

    # Third lot: 20 shares @ €150
    assert lots[2]['shares'] == 20.0
    assert lots[2]['purchase_price'] == 150.0
    assert lots[2]['cost_basis'] == 3000.0
    assert lots[2]['capital_gain'] == 200.0  # 20 * (160 - 150)


def test_fifo_lots_insufficient_shares(share_sell_portfolio: Portfolio) -> None:
    """Test error when trying to sell more shares than available."""
    snapshot = PortfolioSnapshot(share_sell_portfolio, datetime(2024, 12, 31))

    with pytest.raises(InputError, match="Insufficient shares"):
        _calculate_fifo_lots(snapshot, 'depot1', 'sec1', 200.0, 160.0)


def test_calculate_taxes_positive_gain() -> None:
    """Test tax calculation with positive capital gains."""
    tax_rate = 0.25 * (1 + 0.055) * 100  # 26.375%
    taxes = _calculate_taxes(1000.0, 0.0, tax_rate)

    assert taxes['taxable_gain'] == 1000.0
    assert taxes['total_tax'] == 263.75  # 26.375% of 1000


def test_calculate_taxes_with_vorabpauschale_credit() -> None:
    """Test tax calculation with Vorabpauschale credit."""
    tax_rate = 0.25 * (1 + 0.055) * 100  # 26.375%
    taxes = _calculate_taxes(1000.0, 200.0, tax_rate)

    assert taxes['taxable_gain'] == 800.0
    assert taxes['total_tax'] == 211.0  # 26.375% of 800


def test_calculate_taxes_with_higher_rate() -> None:
    """Test tax calculation with higher tax rate (e.g., including church tax)."""
    tax_rate = 0.25 * (1 + 0.055 + 0.09) * 100  # 28.625% (25% + Soli + 9% church tax)
    taxes = _calculate_taxes(1000.0, 0.0, tax_rate)

    assert taxes['taxable_gain'] == 1000.0
    assert taxes['total_tax'] == 286.25  # 28.625% of 1000


def test_calculate_taxes_negative_gain() -> None:
    """Test tax calculation with capital loss (negative gain)."""
    tax_rate = 0.25 * (1 + 0.055) * 100  # 26.375%
    taxes = _calculate_taxes(-500.0, 0.0, tax_rate)

    assert taxes['taxable_gain'] == 0.0
    assert taxes['total_tax'] == 0.0


def test_calculate_taxes_credit_exceeds_gain() -> None:
    """Test when Vorabpauschale credit exceeds capital gain."""
    tax_rate = 0.25 * (1 + 0.055) * 100  # 26.375%
    taxes = _calculate_taxes(500.0, 800.0, tax_rate)

    assert taxes['taxable_gain'] == 0.0
    assert taxes['total_tax'] == 0.0
