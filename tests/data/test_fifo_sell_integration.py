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
from pp_terminal.data.cost_basis import calculate_fifo_sell
from pp_terminal.data.filters import filter_by_account_and_security

from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import TransactionSchema
from pp_terminal.data.tax import calculate_prepaid_tax_per_lot
from pp_terminal.exceptions import InputError
from pp_terminal.data.pp_portfolio_builder import PpPortfolioBuilder
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot

TEST_TAX_RATE = 26.375


@pytest.fixture(name='partial_sell_portfolio')
def provide_partial_sell_portfolio(request: pytest.FixtureRequest) -> Portfolio:
    """Load the partial_sell fixture with realistic buy/sell transactions."""
    fixture_path = request.path.parent.parent / 'fixtures' / 'partial_sell.ids.xml'
    return PpPortfolioBuilder().construct(fixture_path)


def test_partial_sell_remaining_shares(partial_sell_portfolio: Portfolio) -> None:
    """Test selling remaining shares after a partial sell."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))

    # After selling 40 shares, 60 shares remain at 60€ each
    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')
    lots = calculate_fifo_sell(transactions, snapshot.date, sell_price=60.0, shares_to_sell=60.0, tax_rate=TEST_TAX_RATE)

    # All remaining 60 shares come from the original purchase at 5€
    assert len(lots) == 1
    assert lots.iloc[0]['shares'] == 60.0
    assert lots.iloc[0]['purchasePrice'] == 5.0
    assert lots.iloc[0]['costBasis'] == 300.0
    assert lots.iloc[0]['capitalGain'] == 3300.0  # 60 * (60 - 5)


def test_partial_sell_insufficient_shares_error(partial_sell_portfolio: Portfolio) -> None:
    """Test error when trying to sell more shares than were ever purchased."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    # Only 100 shares were purchased, trying to sell 150 should fail
    with pytest.raises(InputError, match="Insufficient shares"):
        calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=150.0, sell_price=60.0, tax_rate=TEST_TAX_RATE)


def test_sell_on_purchase_date(partial_sell_portfolio: Portfolio) -> None:
    """Test selling shares on the same day as purchase."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2023, 12, 30))
    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    # Sell 10 shares on the same day they were purchased at 5€
    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=10.0, sell_price=5.0, tax_rate=TEST_TAX_RATE)

    assert len(lots) == 1
    assert lots.iloc[0]['shares'] == 10.0
    assert lots.iloc[0]['purchasePrice'] == 5.0
    assert lots.iloc[0]['capitalGain'] == 0.0  # No gain when selling at purchase price


def test_capital_loss_scenario(partial_sell_portfolio: Portfolio) -> None:
    """Test selling at a loss (price below purchase price)."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    # Sell at 4€, below purchase price of 5€
    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=20.0, sell_price=4.0, tax_rate=TEST_TAX_RATE)

    assert len(lots) == 1
    assert lots.iloc[0]['shares'] == 20.0
    assert lots.iloc[0]['purchasePrice'] == 5.0
    assert lots.iloc[0]['capitalGain'] == -20.0  # 20 * (4 - 5)


def test_no_vorabpauschale_credit_same_year_sale(partial_sell_portfolio: Portfolio) -> None:
    """Test Vorabpauschale credit is zero when selling in same year as purchase."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2023, 12, 30))
    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=10.0, sell_price=50.0, tax_rate=TEST_TAX_RATE)

    # No Vorabpauschale credit for same-year sale (no CSV provided)
    credit = float(calculate_prepaid_tax_per_lot(lots, datetime(2023, 12, 30), None).sum())

    assert credit == 0.0


def test_empty_transactions() -> None:
    df = calculate_fifo_sell(TransactionSchema.empty(), datetime.now(), shares_to_sell=10.0, sell_price=60.0, tax_rate=TEST_TAX_RATE)

    assert df.empty


def test_zero_price_error(partial_sell_portfolio: Portfolio) -> None:
    """Test handling of zero sale price."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    transactions = snapshot.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    # Zero price should work but result in negative capital gain
    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=10.0, sell_price=0.0, tax_rate=TEST_TAX_RATE)

    assert lots.iloc[0]['capitalGain'] == -50.0  # 10 * (0 - 5)


def test_very_small_shares(partial_sell_portfolio: Portfolio) -> None:
    """Test selling fractional shares."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    transactions = snapshot.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    # Sell 0.5 shares
    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=0.5, sell_price=60.0, tax_rate=TEST_TAX_RATE)

    assert len(lots) == 1
    assert lots.iloc[0]['shares'] == 0.5
    assert lots.iloc[0]['costBasis'] == 2.5  # 0.5 * 5
    assert lots.iloc[0]['capitalGain'] == 27.5  # 0.5 * (60 - 5)


def test_exact_share_match(partial_sell_portfolio: Portfolio) -> None:
    """Test selling exactly all available shares."""
    snapshot = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    transactions = snapshot.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    # Sell exactly 60 shares (all remaining)
    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=60.0, sell_price=60.0, tax_rate=TEST_TAX_RATE)

    assert len(lots) == 1
    assert lots.iloc[0]['shares'] == 60.0
    total_shares = lots['shares'].sum()
    assert total_shares == 60.0


def test_snapshot_at_different_dates(partial_sell_portfolio: Portfolio) -> None:
    """Test snapshots at different dates show correct holdings."""

    # Before any purchases
    snapshot_before = PortfolioSnapshot(partial_sell_portfolio, datetime(2023, 12, 29))
    transactions = snapshot_before.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')
    lots = calculate_fifo_sell(transactions, snapshot_before.date, shares_to_sell=10.0, sell_price=50.0, tax_rate=TEST_TAX_RATE)
    assert lots.empty

    # After purchase, before sell - should have 100 shares
    snapshot_mid = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 1, 1))
    transactions = snapshot_mid.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')
    lots = calculate_fifo_sell(transactions, snapshot_mid.date, shares_to_sell=100.0, sell_price=50.0, tax_rate=TEST_TAX_RATE)
    assert lots['shares'].sum() == 100.0

    # After sell - should have 60 shares
    snapshot_after = PortfolioSnapshot(partial_sell_portfolio, datetime(2024, 12, 31))
    transactions = snapshot_after.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')
    lots = calculate_fifo_sell(transactions, snapshot_after.date, shares_to_sell=60.0, sell_price=60.0, tax_rate=TEST_TAX_RATE)
    assert lots['shares'].sum() == 60.0


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
    transactions = partial_sell_portfolio.securities_account_transactions.pipe(
        filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')
    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=50.0, sell_price=60.0, tax_rate=TEST_TAX_RATE, tax_csv_data=csv_data)

    tax = lots['prepaidTax'].sum()

    # Expected calculation:
    # Lot: 50 shares purchased 2023-12-30
    # Year 2023: 50 * 0.1 * (13-12)/12 = 50 * 0.1 * 1/12 = 0.41666...  (purchased in December = 1 month)
    # Year 2024: 50 * 0.2 * 1.0 = 10.0  (full year)
    # Total: 10.41666...
    assert abs(tax - 10.41666) < 0.01


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
    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, account_id='test-portfolio-uuid-001', security_id='test-security-uuid-001')

    lots = calculate_fifo_sell(transactions, snapshot.date, shares_to_sell=50.0, sell_price=60.0, tax_rate=TEST_TAX_RATE, tax_csv_data=csv_data)

    credit = float(calculate_prepaid_tax_per_lot(lots, datetime(2025, 3, 1), csv_data).sum())

    # Only 2024 has data: 50 * 0.2 * 1.0 = 10.0
    # 2023 is missing, so 0.0 is used
    assert abs(credit - 10.0) < 0.01
