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

import pandas as pd
import pytest

from pp_terminal.data.cost_basis import calculate_total_cost
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType


def test_only_purchases_no_sells(portfolio_with_purchases: Portfolio) -> None:
    """Test cost basis with only purchases (no sells)."""
    cost_basis = calculate_total_cost(portfolio_with_purchases.securities_account_transactions, 'sec-1')

    # Lot 1: 10 shares @ €100 = €1,000
    # Lot 2: 10 shares @ €150 = €1,500
    # Lot 3: 5 shares @ €0 = €0
    # Lot 4: 20 shares @ €100 = €2,000
    # Total: €4,500
    assert cost_basis == pytest.approx(4500.0, abs=0.01)

def test_purchases_and_sells(portfolio_with_sells: Portfolio) -> None:
    cost_basis = calculate_total_cost(portfolio_with_sells.securities_account_transactions, 'sec-1')

    assert cost_basis == pytest.approx(4500.0, abs=0.01)


def test_no_transactions() -> None:
    """Test with portfolio that has no transactions."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
    accounts.index.name = 'accountId'

    portfolio = Portfolio(accounts=accounts, transactions=None, securities=None, prices=None)

    cost_basis = calculate_total_cost(portfolio.securities_account_transactions, 'sec-1')

    assert cost_basis == 0.0

def test_no_purchases_for_security(portfolio_with_purchases: Portfolio) -> None:
    """Test with security that has no purchases."""
    cost_basis = calculate_total_cost(portfolio_with_purchases.securities_account_transactions, 'non-existent-security')

    assert cost_basis == 0.0
