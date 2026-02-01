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
# pylint: disable=duplicate-code

import logging
from datetime import datetime

import pandas as pd
import pytest
from _pytest.logging import LogCaptureFixture

from pp_terminal.data.cost_basis import calculate_total_cost_basis
from pp_terminal.data.filters import filter_by_security
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType, TransactionType


def test_only_purchases_no_sells(portfolio_with_purchases: Portfolio) -> None:
    """Test cost basis with only purchases (no sells)."""
    cost_basis = calculate_total_cost_basis(portfolio_with_purchases.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    # Lot 1: 10 shares @ €100 = €1,000
    # Lot 2: 10 shares @ €150 = €1,500
    # Lot 3: 5 shares @ €0 = €0
    # Lot 4: 20 shares @ €100 = €2,000
    # Total: €4,500
    assert cost_basis == pytest.approx(4500.0, abs=0.01)

def test_purchases_and_sells(portfolio_with_sells: Portfolio) -> None:
    cost_basis = calculate_total_cost_basis(portfolio_with_sells.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    # Purchases:
    #   2020-01-15: acc-1, 10 shares @ €100 = €1,000
    #   2020-06-20: acc-1, 10 shares @ €150 = €1,500
    #   2021-03-10: acc-2, 5 shares @ €0 = €0
    #   2022-01-05: acc-1, 20 shares @ €100 = €2,000
    # Sales:
    #   2020-12-01: acc-1, 7 shares (consumes 7 from lot 1)
    #   2023-06-15: acc-2, 3 shares (consumes 3 from lot 3)
    # Remaining:
    #   Lot 1: 3 shares @ €100 = €300
    #   Lot 2: 10 shares @ €150 = €1,500
    #   Lot 3: 2 shares @ €0 = €0
    #   Lot 4: 20 shares @ €100 = €2,000
    # Total: €3,800
    assert cost_basis == pytest.approx(3800.0, abs=0.01)


def test_no_transactions() -> None:
    """Test with portfolio that has no transactions."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
    accounts.index.name = 'accountId'

    portfolio = Portfolio(accounts=accounts, transactions=None, securities=None, prices=None)

    cost_basis = calculate_total_cost_basis(portfolio.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    assert cost_basis == 0.0

def test_no_purchases_for_security(portfolio_with_purchases: Portfolio) -> None:
    """Test with security that has no purchases."""
    cost_basis = calculate_total_cost_basis(portfolio_with_purchases.securities_account_transactions.pipe(filter_by_security, security_id='non-existent-security'))

    assert cost_basis == 0.0


def test_all_shares_sold(portfolio_with_purchases: Portfolio) -> None:
    """Test cost basis when all shares have been sold."""
    transactions = portfolio_with_purchases.securities_account_transactions.copy()

    # Add sales that exhaust all lots
    sales = pd.DataFrame([
        [datetime(2023, 1, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 2000.0, 20.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # Sell lot 1 (10) + lot 2 (10)
        [datetime(2023, 2, 1), 'acc-2', 'sec-1', TransactionType.SELL.value, 500.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # Sell lot 3 (5)
        [datetime(2023, 3, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 2000.0, 20.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # Sell lot 4 (20)
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    transactions = pd.concat([transactions, sales])

    cost_basis = calculate_total_cost_basis(transactions.pipe(filter_by_security, security_id='sec-1'))

    assert cost_basis == 0.0


def test_sell_exceeds_purchases(portfolio_with_purchases: Portfolio, caplog: LogCaptureFixture) -> None:
    """Test cost basis when sells exceed available shares (partial matching)."""
    transactions = portfolio_with_purchases.securities_account_transactions.copy()

    # Try to sell more shares than available from acc-1
    sales = pd.DataFrame([
        [datetime(2023, 1, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 5000.0, 50.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # Try to sell 50, only 40 available in acc-1
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    transactions = pd.concat([transactions, sales])

    with caplog.at_level(logging.WARNING):
        cost_basis = calculate_total_cost_basis(transactions.pipe(filter_by_security, security_id='sec-1'))

    # Should only match the 40 shares available in acc-1, leaving acc-2's 5 shares
    # Remaining: 5 shares @ €0 (lot 3 from acc-2) = €0
    assert cost_basis == pytest.approx(0.0, abs=0.01)
    assert 'could not be fully matched' in caplog.text


def test_multiple_securities(portfolio_with_purchases: Portfolio) -> None:
    """Test cost basis correctly filters by security_id."""
    transactions = portfolio_with_purchases.securities_account_transactions.copy()

    # Add transactions for a second security
    sec2_transactions = pd.DataFrame([
        [datetime(2020, 1, 1), 'acc-1', 'sec-2', TransactionType.BUY.value, -3000.0, 30.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # 30 shares @ 100
        [datetime(2020, 6, 1), 'acc-1', 'sec-2', TransactionType.SELL.value, 1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # Sell 10 shares
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    sec2_transactions = sec2_transactions.set_index(['date', 'accountId', 'securityId'])

    transactions = pd.concat([transactions, sec2_transactions])

    # Calculate cost basis for sec-1 (should ignore sec-2)
    cost_basis_sec1 = calculate_total_cost_basis(transactions.pipe(filter_by_security, security_id='sec-1'))
    assert cost_basis_sec1 == pytest.approx(4500.0, abs=0.01)

    # Calculate cost basis for sec-2 (30 - 10 = 20 shares @ €100 = €2,000)
    cost_basis_sec2 = calculate_total_cost_basis(transactions.pipe(filter_by_security, security_id='sec-2'))
    assert cost_basis_sec2 == pytest.approx(2000.0, abs=0.01)


def test_cost_basis_with_fees() -> None:
    """Test that transaction fees are included in cost basis calculation."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['acc-1'])
    accounts.index.name = 'accountId'

    # Purchase with fees: amount = -1000, fees = 10, shares = 10
    # purchasePrice = 1000 / 10 = 100 per share (actual market price)
    # costBasis = 100 * 10 + 10 = 1010 (includes fees)
    transactions = pd.DataFrame([
        [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 10.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=None, prices=None)
    cost_basis = calculate_total_cost_basis(portfolio.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    # Total cost basis: (10 shares * 100) + 10 fees = 1010
    assert cost_basis == pytest.approx(1010.0, abs=0.01)


def test_cost_basis_with_fees_and_sells() -> None:
    """Test that fees are properly allocated during FIFO matching with partial lot sales."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['acc-1'])
    accounts.index.name = 'accountId'

    # Lot 1: purchasePrice = 1000 / 10 = 100, fees = 20, shares = 10
    # Lot 2: purchasePrice = 1500 / 10 = 150, fees = 30, shares = 10
    # Sell 7 shares (consumes 7 from lot 1, fees proportionally reduced to 6)
    # Remaining lot 1: 3 shares @ 100 + 6 fees = 306
    # Remaining lot 2: 10 shares @ 150 + 30 fees = 1530
    # Total: 1836
    transactions = pd.DataFrame([
        [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 20.0],
        [datetime(2020, 6, 20), 'acc-1', 'sec-1', TransactionType.BUY.value, -1500.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 30.0],
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1400.0, 7.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=None, prices=None)
    cost_basis = calculate_total_cost_basis(portfolio.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    assert cost_basis == pytest.approx(1836.0, abs=0.01)


def test_cost_basis_with_mixed_fees() -> None:
    """Test cost basis with some transactions having fees and others not."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['acc-1'])
    accounts.index.name = 'accountId'

    # Lot 1: purchasePrice = 100, no fees (None treated as 0), shares = 10 → costBasis = 1000
    # Lot 2: purchasePrice = 150, fees = 30, shares = 10 → costBasis = 1500 + 30 = 1530
    # Lot 3: purchasePrice = 100, fees = 0 (explicit), shares = 20 → costBasis = 2000
    transactions = pd.DataFrame([
        [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, None],  # No fees (None)
        [datetime(2020, 6, 20), 'acc-1', 'sec-1', TransactionType.BUY.value, -1500.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 30.0],  # With fees
        [datetime(2022, 1, 5), 'acc-1', 'sec-1', TransactionType.BUY.value, -2000.0, 20.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],  # Explicit 0 fees
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=None, prices=None)
    cost_basis = calculate_total_cost_basis(portfolio.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    # Total: (10*100 + 0) + (10*150 + 30) + (20*100 + 0) = 1000 + 1530 + 2000 = 4530
    assert cost_basis == pytest.approx(4530.0, abs=0.01)


def test_cost_basis_delivery_inbound_with_fees() -> None:
    """Test cost basis for DELIVERY_INBOUND transactions with fees (e.g., transfer fees)."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['acc-1'])
    accounts.index.name = 'accountId'

    # DELIVERY_INBOUND with transfer fee: amount = 0 (gift), fees = 25, shares = 5
    # purchasePrice = 0 / 5 = 0 per share (no purchase price)
    # costBasis = 0 * 5 + 25 = 25 (only transfer fees)
    transactions = pd.DataFrame([
        [datetime(2021, 3, 10), 'acc-1', 'sec-1', TransactionType.DELIVERY_INBOUND.value, 0.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0, 25.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=None, prices=None)
    cost_basis = calculate_total_cost_basis(portfolio.securities_account_transactions.pipe(filter_by_security, security_id='sec-1'))

    # Total cost basis: (5 shares * 0) + 25 fees = 25
    assert cost_basis == pytest.approx(25.0, abs=0.01)
