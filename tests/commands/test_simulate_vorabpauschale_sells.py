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
from _pytest.fixtures import TopRequest
from pandas.testing import assert_frame_equal
import pytest

from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.data.pp_portfolio_builder import PpPortfolioBuilder
from pp_terminal.domain.schemas import TransactionType, AccountType
from pp_terminal.commands.simulate_vorabpauschale import calculate


@pytest.fixture(name='sell_test_accounts')
def provide_sell_test_accounts() -> pd.DataFrame:
    accounts = pd.DataFrame([
        ['Depot', AccountType.SECURITIES.value, 'EUR', None],
    ], columns=['name', 'type', 'currency', 'referenceAccount'], index=['1'])
    accounts.index.name = 'accountId'
    return accounts


@pytest.fixture(name='sell_test_securities')
def provide_sell_test_securities() -> pd.DataFrame:
    securities = pd.DataFrame([
        ['Test ETF', 'A1234', 'EUR']
    ], columns=['name', 'wkn', 'currency'], index=['sec1'])
    securities.index.name = 'securityId'
    return securities


@pytest.fixture(name='sell_test_prices')
def provide_sell_test_prices() -> pd.DataFrame:
    return pd.DataFrame([
        [datetime(2023, 12, 31), 'sec1', 50.0],
        [datetime(2024, 12, 31), 'sec1', 60.0],
    ], columns=['date', 'securityId', 'price']).set_index(['date', 'securityId'])


def test_full_sell_during_year(sell_test_accounts: pd.DataFrame, sell_test_securities: pd.DataFrame, sell_test_prices: pd.DataFrame) -> None:
    """
    Test case: Full sell during year (all shares sold)

    Expected: No Vorabpauschale as no shares held at year end
    """
    transactions = pd.DataFrame([
        [datetime(2023, 6, 1), TransactionType.BUY.value, 5000.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
        [datetime(2024, 8, 1), TransactionType.SELL.value, 6000.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'type', 'amount', 'shares', 'securityId', 'accountId', 'accountType', 'currency', 'taxes']).set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(sell_test_accounts, transactions, sell_test_securities, sell_test_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375)

    assert result is None


def test_partial_sell_during_year(sell_test_accounts: pd.DataFrame, sell_test_securities: pd.DataFrame, sell_test_prices: pd.DataFrame) -> None:
    """
    Test case: Partial sell during year (50 of 100 shares sold)

    Scenario:
    - Jan 1: Hold 100 shares at 50 EUR = 5000 EUR
    - Aug 1: Sell 50 shares
    - Dec 31: Hold 50 shares at 60 EUR = 3000 EUR

    Expected calculation (for 50 remaining shares):
    - Begin value: 50 * 50 = 2500 EUR
    - End value: 50 * 60 = 3000 EUR
    - Outcome: 500 EUR
    - Base yield: 2500 * 0.0229 * 0.7 = 40.08 EUR
    - Vorabpauschale: min(500, 40.08) = 40.08 EUR
    - After tax (26.375%): 10.57 EUR
    - Note: Exemption not applied because securities DataFrame doesn't have 'exempt_rate' column
    """
    transactions = pd.DataFrame([
        [datetime(2023, 6, 1), TransactionType.BUY.value, 5000.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
        [datetime(2024, 8, 1), TransactionType.SELL.value, 3000.0, 50.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'type', 'amount', 'shares', 'securityId', 'accountId', 'accountType', 'currency', 'taxes']).set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(sell_test_accounts, transactions, sell_test_securities, sell_test_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375, 30)

    assert result is not None
    result_security = result[result['name'] == 'Test ETF']

    expected_df = pd.DataFrame([
        ['A1234', 'Test ETF', 'EUR', 10.57]
    ], columns=['wkn', 'name', 'currency', 'Depot'], index=['sec1'])
    expected_df.index.name = 'securityId'

    assert_frame_equal(expected_df, result_security.round(2))


def test_multiple_sells_during_year(sell_test_accounts: pd.DataFrame, sell_test_securities: pd.DataFrame, sell_test_prices: pd.DataFrame) -> None:
    """
    Test case: Multiple sells during year (100→75→50 shares)

    Expected: Same as partial sell (only 50 remaining shares matter)
    """
    transactions = pd.DataFrame([
        [datetime(2023, 6, 1), TransactionType.BUY.value, 5000.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
        [datetime(2024, 3, 1), TransactionType.SELL.value, 1500.0, 25.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
        [datetime(2024, 9, 1), TransactionType.SELL.value, 1500.0, 25.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'type', 'amount', 'shares', 'securityId', 'accountId', 'accountType', 'currency', 'taxes']).set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(sell_test_accounts, transactions, sell_test_securities, sell_test_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375, 30)

    assert result is not None
    result_security = result[result['name'] == 'Test ETF']

    expected_df = pd.DataFrame([
        ['A1234', 'Test ETF', 'EUR', 10.57]
    ], columns=['wkn', 'name', 'currency', 'Depot'], index=['sec1'])
    expected_df.index.name = 'securityId'

    assert_frame_equal(expected_df, result_security.round(2))


def test_sell_and_rebuy_during_year(sell_test_accounts: pd.DataFrame, sell_test_securities: pd.DataFrame, sell_test_prices: pd.DataFrame) -> None:
    """
    Test case: Sell all, then buy new shares during year

    Scenario:
    - Jan 1: Hold 100 shares at 50 EUR = 5000 EUR
    - Apr 1: Sell all 100 shares
    - Aug 1: Buy 50 shares at 60 EUR
    - Dec 31: Hold 50 shares at 60 EUR = 3000 EUR

    Expected calculation:
    - These 50 shares were bought in Aug (month 8)
    - Pro-rata: 5 months held (Aug-Dec)
    - Pro-rata shares: 50 * 5/12 = 20.83
    - Modified begin value: 20.83 * 50 = 1041.50 EUR
    - End value: 3000 EUR
    - Outcome: 3000 EUR (no shares at begin)
    - Base yield: 1041.50 * 0.0229 * 0.7 = 16.66 EUR
    - Vorabpauschale: min(3000, 16.66) = 16.66 EUR
    - After tax: 16.66 * 0.26375 = 4.39 EUR
    - Note: Exemption not applied because securities DataFrame doesn't have 'exempt_rate' column
    """
    transactions = pd.DataFrame([
        [datetime(2023, 6, 1), TransactionType.BUY.value, 5000.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
        [datetime(2024, 4, 1), TransactionType.SELL.value, 5500.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
        [datetime(2024, 8, 1), TransactionType.BUY.value, 3000.0, 50.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'type', 'amount', 'shares', 'securityId', 'accountId', 'accountType', 'currency', 'taxes']).set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(sell_test_accounts, transactions, sell_test_securities, sell_test_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375, 30)

    assert result is not None
    result_security = result[result['name'] == 'Test ETF']

    expected_df = pd.DataFrame([
        ['A1234', 'Test ETF', 'EUR', 4.40]
    ], columns=['wkn', 'name', 'currency', 'Depot'], index=['sec1'])
    expected_df.index.name = 'securityId'

    assert_frame_equal(expected_df, result_security.round(2))


def test_no_sells_baseline(sell_test_accounts: pd.DataFrame, sell_test_securities: pd.DataFrame, sell_test_prices: pd.DataFrame) -> None:
    """
    Baseline test: No sells, just hold

    This should pass with current implementation
    """
    transactions = pd.DataFrame([
        [datetime(2023, 6, 1), TransactionType.BUY.value, 5000.0, 100.0, 'sec1', '1', AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'type', 'amount', 'shares', 'securityId', 'accountId', 'accountType', 'currency', 'taxes']).set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(sell_test_accounts, transactions, sell_test_securities, sell_test_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375, 30)

    # Calculation:
    # Begin: 100 * 50 = 5000
    # End: 100 * 60 = 6000
    # Outcome: 1000
    # Base yield: 5000 * 0.0229 * 0.7 = 80.15
    # Vorabpauschale: min(1000, 80.15) = 80.15
    # After tax: 80.15 * 0.26375 = 21.14
    # Note: Exemption not applied because securities DataFrame doesn't have 'exempt_rate' column

    assert result is not None

    # Filter to just the security row (exclude "Related Account Balance")
    result_security = result[result['name'] == 'Test ETF']

    expected_df = pd.DataFrame([
        ['A1234', 'Test ETF', 'EUR', 21.14]
    ], columns=['wkn', 'name', 'currency', 'Depot'], index=['sec1'])
    expected_df.index.name = 'securityId'

    assert_frame_equal(expected_df, result_security.round(2))


def test_partial_sell_from_xml_fixture(request: TopRequest) -> None:
    """
    Integration test: Verify SELL transactions from XML are correctly parsed and handled

    Scenario from partial_sell.ids.xml:
    - 2023-12-30: BUY 100 shares at 50 EUR = 5000 EUR
    - 2024-01-02: Price = 50 EUR (year start)
    - 2024-08-15: SELL 40 shares at 55 EUR
    - 2024-12-31: Price = 60 EUR, holding 60 shares = 3600 EUR

    Expected calculation (for 60 remaining shares):
    - Begin value: 60 * 50 = 3000 EUR (only continuously held shares)
    - End value: 60 * 60 = 3600 EUR
    - Outcome: 600 EUR
    - Base yield: 3000 * 0.0229 * 0.7 = 48.09 EUR
    - Vorabpauschale: min(600, 48.09) = 48.09 EUR
    - After tax (26.375%): 48.09 * 0.26375 = 12.68 EUR
    - After exemption (30% default): 12.68 * 0.70 = 8.88 EUR
    """
    portfolio = PpPortfolioBuilder().construct(request.path.parent.parent / 'fixtures' / 'partial_sell.ids.xml')

    # Verify transactions are parsed correctly
    txns = portfolio.securities_account_transactions
    assert txns is not None
    assert len(txns) == 2

    # Verify BUY transaction
    buy_txn = txns[txns['type'] == 'BUY']
    assert len(buy_txn) == 1
    assert float(buy_txn.iloc[0]['shares']) == 100.0

    # Verify SELL transaction is correctly parsed
    sell_txn = txns[txns['type'] == 'SELL']
    assert len(sell_txn) == 1
    assert float(sell_txn.iloc[0]['shares']) == 40.0
    assert sell_txn.index.get_level_values('date')[0].year == 2024

    # Calculate vorabpauschale
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375, 30)

    assert result is not None

    # Filter to just the security row (exclude "Related Account Balance")
    result_security = result[result['name'] == 'Test World ETF']

    expected_df = pd.DataFrame([
        ['TEST01', 'Test World ETF', 'EUR', 12.68]
    ], columns=['wkn', 'name', 'currency', 'Test Depot'], index=['test-security-uuid-001'])
    expected_df.index.name = 'securityId'

    assert_frame_equal(expected_df, result_security.round(2))
