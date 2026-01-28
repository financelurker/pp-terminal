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

from datetime import datetime

import pandas as pd
import pytest

from pp_terminal.data.cost_basis import calculate_current_cost_basis
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType, TransactionType


def test_only_purchases_no_sales(portfolio_with_purchases: Portfolio) -> None:
    """Test cost basis with only purchases (no sales)."""
    cost_basis = calculate_current_cost_basis(portfolio_with_purchases, 'sec-1')

    # Lot 1: 10 shares @ €100 = €1,000
    # Lot 2: 10 shares @ €150 = €1,500
    # Lot 3: 5 shares @ €0 = €0
    # Lot 4: 20 shares @ €100 = €2,000
    # Total: €4,500
    assert cost_basis == pytest.approx(4500.0, abs=0.01)

def test_purchases_and_sales(portfolio_with_sales: Portfolio) -> None:
    """Test cost basis with purchases and sales (FIFO matching)."""
    cost_basis = calculate_current_cost_basis(portfolio_with_sales, 'sec-1')

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

def test_with_tax_credit(portfolio_with_purchases: Portfolio, tax_csv_data: pd.DataFrame) -> None:
    """Test cost basis net of tax credit."""
    evaluation_date = datetime(2022, 12, 31)
    cost_basis = calculate_current_cost_basis(
        portfolio_with_purchases,
        'sec-1',
        tax_csv_data=tax_csv_data,
        evaluation_date=evaluation_date
    )

    # Gross cost basis: €4,500 (from test_only_purchases_no_sales)
    # Tax credit calculation:
    #   Lot 1 (2020-01-15, acc-1, 10 shares):
    #     2020: 10 * €0.05 * (13-1)/12 = €0.50
    #     2021: 10 * €0.06 = €0.60
    #   Lot 2 (2020-06-20, acc-1, 10 shares):
    #     2020: 10 * €0.05 * (13-6)/12 = €0.29
    #     2021: 10 * €0.06 = €0.60
    #   Lot 3 (2021-03-10, acc-2, 5 shares):
    #     2021: 5 * €0.06 * (13-3)/12 = €0.25
    #   Lot 4 (2022-01-05, acc-1, 20 shares):
    #     No credit (purchased in 2022, evaluated in 2022)
    # Total tax credit: €2.24
    # Net cost basis: €4,500 - €2.24 = €4,497.76
    expected_credit = (
        10 * 0.05 * (13-1)/12 +  # Lot 1, 2020
        10 * 0.06 +               # Lot 1, 2021
        10 * 0.05 * (13-6)/12 +  # Lot 2, 2020
        10 * 0.06 +               # Lot 2, 2021
        5 * 0.06 * (13-3)/12      # Lot 3, 2021
    )
    assert cost_basis == pytest.approx(4500.0 - expected_credit, abs=0.01)

def test_all_shares_sold(portfolio_with_sales: Portfolio) -> None:
    """Test that cost basis is zero when all shares are sold."""
    if not isinstance(portfolio_with_sales.securities_account_transactions, pd.DataFrame):
        raise TypeError('transactions must be a DataFrame')

    # Add more sales to sell everything
    transactions = portfolio_with_sales.securities_account_transactions.copy()

    more_sales = pd.DataFrame([
        [datetime(2024, 1, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 5000.0, 33.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Sell remaining 33 shares
        [datetime(2024, 1, 2), 'acc-2', 'sec-1', TransactionType.SELL.value, 0.0, 2.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Sell remaining 2 from acc-2
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    more_sales = more_sales.set_index(['date', 'accountId', 'securityId'])

    transactions = pd.concat([transactions, more_sales])

    portfolio = Portfolio(
        accounts=portfolio_with_sales.securities_accounts,
        transactions=transactions,
        securities=portfolio_with_sales.securities,
        prices=None
    )

    cost_basis = calculate_current_cost_basis(portfolio, 'sec-1')

    assert cost_basis == 0.0

def test_no_transactions() -> None:
    """Test with portfolio that has no transactions."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
    accounts.index.name = 'accountId'

    portfolio = Portfolio(accounts=accounts, transactions=None, securities=None, prices=None)

    cost_basis = calculate_current_cost_basis(portfolio, 'sec-1')

    assert cost_basis == 0.0

def test_no_purchases_for_security(portfolio_with_purchases: Portfolio) -> None:
    """Test with security that has no purchases."""
    cost_basis = calculate_current_cost_basis(portfolio_with_purchases, 'non-existent-security')

    assert cost_basis == 0.0

def test_net_cost_basis_not_negative(portfolio_with_purchases: Portfolio) -> None:
    """Test that net cost basis is capped at 0 (not negative)."""
    # Create tax CSV with very high tax credits
    high_tax_csv = pd.DataFrame([
        [2020, 'acc-1', 'sec-1', 500.0, 0],  # €500 per share (unrealistically high)
    ], columns=['year', 'account_id', 'security_id', 'tax_per_share', 'tax_free_allowance'])
    high_tax_csv = high_tax_csv.set_index(['year', 'account_id', 'security_id'])

    evaluation_date = datetime(2022, 12, 31)
    cost_basis = calculate_current_cost_basis(
        portfolio_with_purchases,
        'sec-1',
        tax_csv_data=high_tax_csv,
        evaluation_date=evaluation_date
    )

    # Cost basis should be capped at 0, not negative
    assert cost_basis == 0.0
