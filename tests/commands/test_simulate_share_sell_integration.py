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

from datetime import datetime

import pandas as pd
import pytest

from pp_terminal.portfolio import Portfolio
from pp_terminal.schemas import AccountType
from pp_terminal.commands.simulate_share_sell import (
    _calculate_fifo_lots,
    _calculate_taxes,
    _calculate_vorabpauschale_credit_for_lots
)
from pp_terminal.exceptions import InputError
from pp_terminal.pp_portfolio_builder import PpPortfolioBuilder
from pp_terminal.portfolio_snapshot import PortfolioSnapshot


@pytest.fixture(name='partial_sell_portfolio')
def provide_partial_sell_portfolio(request: pytest.FixtureRequest) -> Portfolio:
    """Load the partial_sell fixture with realistic buy/sell transactions."""
    fixture_path = request.path.parent.parent / 'fixtures' / 'partial_sell.ids.xml'
    builder = PpPortfolioBuilder()
    return builder.construct(fixture_path)


def test_partial_sell_remaining_shares(partial_sell_portfolio: Portfolio) -> None:
    """Test selling remaining shares after a partial sell."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # After selling 40 shares, 60 shares remain at 60€ each
    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 60.0, 60.0)

    # All remaining 60 shares come from the original purchase at 5€
    assert len(lots) == 1
    assert lots[0]['shares'] == 60.0
    assert lots[0]['purchase_price'] == 5.0
    assert lots[0]['cost_basis'] == 300.0
    assert lots[0]['capital_gain'] == 3300.0  # 60 * (60 - 5)


def test_partial_sell_insufficient_shares_error(partial_sell_portfolio: Portfolio) -> None:
    """Test error when trying to sell more shares than were ever purchased."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Only 100 shares were purchased, trying to sell 150 should fail
    with pytest.raises(InputError, match="Insufficient shares"):
        _calculate_fifo_lots(snapshot, account_id, security_id, 150.0, 60.0)


def test_sell_on_purchase_date(partial_sell_portfolio: Portfolio) -> None:
    """Test selling shares on the same day as purchase."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2023, 12, 30))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Sell 10 shares on the same day they were purchased at 5€
    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 10.0, 5.0)

    assert len(lots) == 1
    assert lots[0]['shares'] == 10.0
    assert lots[0]['purchase_price'] == 5.0
    assert lots[0]['capital_gain'] == 0.0  # No gain when selling at purchase price


def test_capital_loss_scenario(partial_sell_portfolio: Portfolio) -> None:
    """Test selling at a loss (price below purchase price)."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Sell at 4€, below purchase price of 5€
    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 20.0, 4.0)

    assert len(lots) == 1
    assert lots[0]['shares'] == 20.0
    assert lots[0]['purchase_price'] == 5.0
    assert lots[0]['capital_gain'] == -20.0  # 20 * (4 - 5)


def test_no_vorabpauschale_credit_same_year_sale(partial_sell_portfolio: Portfolio) -> None:
    """Test Vorabpauschale credit is zero when selling in same year as purchase."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2023, 12, 30))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 10.0, 50.0)

    # No Vorabpauschale credit for same-year sale (no CSV provided)
    credit = _calculate_vorabpauschale_credit_for_lots(
        account_id, security_id, lots, datetime(2023, 12, 30), None
    )

    assert credit == 0.0


def test_tax_calculation_with_loss() -> None:
    """Test that no tax is charged on capital losses."""
    tax_rate = 26.375
    taxes = _calculate_taxes(-1000.0, 0.0, tax_rate)

    assert taxes['taxable_gain'] == 0.0
    assert taxes['total_tax'] == 0.0


def test_tax_calculation_vorab_exceeds_gain() -> None:
    """Test when Vorabpauschale credit exceeds capital gain."""
    tax_rate = 26.375
    taxes = _calculate_taxes(500.0, 1000.0, tax_rate)

    assert taxes['taxable_gain'] == 0.0
    assert taxes['total_tax'] == 0.0


def test_nonexistent_security_error(partial_sell_portfolio: Portfolio) -> None:
    """Test error when security doesn't exist."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'nonexistent-security'

    with pytest.raises(InputError, match="No purchase transactions found"):
        _calculate_fifo_lots(snapshot, account_id, security_id, 10.0, 60.0)


def test_nonexistent_account_error(partial_sell_portfolio: Portfolio) -> None:
    """Test error when account doesn't exist."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'nonexistent-account'
    security_id = 'test-security-uuid-001'

    with pytest.raises(InputError, match="No purchase transactions found"):
        _calculate_fifo_lots(snapshot, account_id, security_id, 10.0, 60.0)


def test_empty_portfolio_error() -> None:
    """Test error when portfolio has no transactions."""
    # Create minimal portfolio with no transactions
    accounts = pd.DataFrame([
        ['Test Depot', AccountType.SECURITIES.value, 'account1', False, 'EUR'],
    ], columns=['Name', 'Type', 'Referenceaccount_id', 'is_retired', 'currency'],
    index=['depot1'])
    accounts.index.name = 'account_id'

    securities = pd.DataFrame([
        ['Test ETF', 'TEST01', 'EUR'],
    ], columns=['Name', 'Wkn', 'currency'], index=['sec1'])
    securities.index.name = 'SecurityId'

    # No transactions
    transactions = pd.DataFrame(columns=['date', 'account_id', 'SecurityId', 'Type', 'amount', 'Shares', 'account_type', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'account_id', 'SecurityId'])

    prices = pd.DataFrame([
        [datetime(2024, 12, 31), 'sec1', 100.0],
    ], columns=['date', 'SecurityId', 'Price'])
    prices = prices.set_index(['date', 'SecurityId'])

    portfolio = Portfolio(accounts, transactions, securities, prices)
    portfolio.base_currency = 'EUR'

    snapshot = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    with pytest.raises(InputError, match="No transactions found in portfolio"):
        _calculate_fifo_lots(snapshot, 'depot1', 'sec1', 10.0, 100.0)


def test_zero_price_error(partial_sell_portfolio: Portfolio) -> None:
    """Test handling of zero sale price."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Zero price should work but result in negative capital gain
    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 10.0, 0.0)

    assert lots[0]['capital_gain'] == -50.0  # 10 * (0 - 5)


def test_very_small_shares(partial_sell_portfolio: Portfolio) -> None:
    """Test selling fractional shares."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Sell 0.5 shares
    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 0.5, 60.0)

    assert len(lots) == 1
    assert lots[0]['shares'] == 0.5
    assert lots[0]['cost_basis'] == 2.5  # 0.5 * 5
    assert lots[0]['capital_gain'] == 27.5  # 0.5 * (60 - 5)


def test_exact_share_match(partial_sell_portfolio: Portfolio) -> None:
    """Test selling exactly all available shares."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Sell exactly 60 shares (all remaining)
    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 60.0, 60.0)

    assert len(lots) == 1
    assert lots[0]['shares'] == 60.0
    total_shares = sum(lot['shares'] for lot in lots)
    assert total_shares == 60.0


def test_high_tax_rate() -> None:
    """Test with a higher tax rate including church tax."""
    tax_rate = 0.25 * (1 + 0.055 + 0.09) * 100  # 28.625%
    taxes = _calculate_taxes(10000.0, 0.0, tax_rate)

    assert taxes['taxable_gain'] == 10000.0
    assert taxes['total_tax'] == 2862.5  # 28.625% of 10000


def test_zero_tax_rate() -> None:
    """Test with zero tax rate (edge case)."""
    taxes = _calculate_taxes(1000.0, 0.0, 0.0)

    assert taxes['taxable_gain'] == 1000.0
    assert taxes['total_tax'] == 0.0


def test_snapshot_at_different_dates(partial_sell_portfolio: Portfolio) -> None:
    """Test snapshots at different dates show correct holdings."""
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    # Before any purchases
    snapshot_before = PortfolioSnapshot(partial_sell_portfolio, datetime(2023, 12, 29))
    with pytest.raises(InputError):
        _calculate_fifo_lots(snapshot_before, account_id, security_id, 10.0, 50.0)

    # After purchase, before sell - should have 100 shares
    snapshot_mid = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 1, 1))
    lots = _calculate_fifo_lots(snapshot_mid, account_id, security_id, 100.0, 50.0)
    assert sum(lot['shares'] for lot in lots) == 100.0

    # After sell - should have 60 shares
    snapshot_after = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    lots = _calculate_fifo_lots(snapshot_after, account_id, security_id, 60.0, 60.0)
    assert sum(lot['shares'] for lot in lots) == 60.0


def test_vorabpauschale_csv_calculation(partial_sell_portfolio: Portfolio) -> None:
    """Test Vorabpauschale credit calculation from CSV with month proration."""
    # Create test CSV data
    csv_data = pd.DataFrame({
        'year': [2023, 2024],
        'account_id': ['test-portfolio-uuid-001', 'test-portfolio-uuid-001'],
        'security_id': ['test-security-uuid-001', 'test-security-uuid-001'],
        'tax_per_share': [0.1, 0.2]
    })
    csv_data = csv_data.set_index(['year', 'account_id', 'security_id'])

    # Purchase 100 shares on Dec 30, 2023, sell 50 shares on March 1, 2025
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2025, 3, 1))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 50.0, 60.0)

    # Calculate credit
    credit = _calculate_vorabpauschale_credit_for_lots(
        account_id, security_id, lots, datetime(2025, 3, 1), csv_data
    )

    # Expected calculation:
    # Lot: 50 shares purchased 2023-12-30
    # Year 2023: 50 * 0.1 * (13-12)/12 = 50 * 0.1 * 1/12 = 0.41666...  (purchased in December = 1 month)
    # Year 2024: 50 * 0.2 * 1.0 = 10.0  (full year)
    # Total: 10.41666...
    assert abs(credit - 10.41666) < 0.01


def test_vorabpauschale_csv_missing_data(partial_sell_portfolio: Portfolio) -> None:
    """Test Vorabpauschale credit when CSV has missing years (should use 0.0 silently)."""
    # Create test CSV with only 2024 data (missing 2023)
    csv_data = pd.DataFrame({
        'year': [2024],
        'account_id': ['test-portfolio-uuid-001'],
        'security_id': ['test-security-uuid-001'],
        'tax_per_share': [0.2]
    })
    csv_data = csv_data.set_index(['year', 'account_id', 'security_id'])

    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2025, 3, 1))
    account_id = 'test-portfolio-uuid-001'
    security_id = 'test-security-uuid-001'

    lots = _calculate_fifo_lots(snapshot, account_id, security_id, 50.0, 60.0)

    credit = _calculate_vorabpauschale_credit_for_lots(
        account_id, security_id, lots, datetime(2025, 3, 1), csv_data
    )

    # Only 2024 has data: 50 * 0.2 * 1.0 = 10.0
    # 2023 is missing, so 0.0 is used
    assert abs(credit - 10.0) < 0.01
