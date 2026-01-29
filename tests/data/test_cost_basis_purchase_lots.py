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
from pandera.typing import DataFrame

from pp_terminal.data.cost_basis import calculate_purchase_lots
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType, TransactionType, AccountSchema, SecuritySchema, TransactionSchema


def test_single_purchase() -> None:
    """Test with single purchase transaction."""
    accounts = DataFrame[AccountSchema]([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
    accounts.index.name = 'accountId'

    securities = DataFrame[SecuritySchema]([
        ['Test Security', 'XXX', 'ISIN123', None, False, 'EUR'],
    ], columns=['name', 'wkn', 'isin', 'note', 'isRetired', 'currency'], index=['sec-1'])
    securities.index.name = 'securityId'

    transactions = DataFrame[TransactionSchema]([
        [TransactionType.BUY.value, -1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['type', 'amount', 'shares', 'accountType', 'currency', 'taxes'],
        index=pd.MultiIndex.from_arrays([[datetime(2020, 1, 15)], ['acc-1'], ['sec-1']], names=['date', 'accountId', 'securityId']))

    portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=securities, prices=None)

    lots = calculate_purchase_lots(portfolio, 'sec-1')

    assert len(lots) == 1
    assert lots.iloc[0]['account_id'] == 'acc-1'
    assert lots.iloc[0]['shares'] == 10.0
    assert lots.iloc[0]['purchase_price'] == 100.0
    assert lots.iloc[0]['cost_basis'] == 1000.0

def test_multiple_purchases_sorted_by_date(portfolio_with_purchases: Portfolio) -> None:
    """Test that multiple purchases are sorted by date (FIFO order)."""
    lots = calculate_purchase_lots(portfolio_with_purchases, 'sec-1', sort_by_date=True)

    assert len(lots) == 4
    assert lots.iloc[0]['purchase_date'] == datetime(2020, 1, 15)
    assert lots.iloc[1]['purchase_date'] == datetime(2020, 6, 20)
    assert lots.iloc[2]['purchase_date'] == datetime(2021, 3, 10)
    assert lots.iloc[3]['purchase_date'] == datetime(2022, 1, 5)

def test_multiple_accounts(portfolio_with_purchases: Portfolio) -> None:
    """Test purchases across multiple accounts."""
    lots = calculate_purchase_lots(portfolio_with_purchases, 'sec-1')

    acc1_lots = lots[lots['account_id'] == 'acc-1']
    acc2_lots = lots[lots['account_id'] == 'acc-2']

    assert len(acc1_lots) == 3
    assert len(acc2_lots) == 1

def test_delivery_inbound_included(portfolio_with_purchases: Portfolio) -> None:
    """Test that DELIVERY_INBOUND transactions are included."""
    lots = calculate_purchase_lots(portfolio_with_purchases, 'sec-1')

    delivery_lot = lots[lots['purchase_date'] == datetime(2021, 3, 10)].iloc[0]
    assert delivery_lot['shares'] == 5.0
    assert delivery_lot['purchase_price'] == 0.0
    assert delivery_lot['cost_basis'] == 0.0

def test_no_transactions() -> None:
    """Test with portfolio that has no transactions."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
    accounts.index.name = 'accountId'

    portfolio = Portfolio(accounts=accounts, transactions=None, securities=None, prices=None)

    lots = calculate_purchase_lots(portfolio, 'sec-1')

    assert lots.empty

def test_no_purchases_for_security(portfolio_with_purchases: Portfolio) -> None:
    """Test with security that has no purchases."""
    lots = calculate_purchase_lots(portfolio_with_purchases, 'non-existent-security')

    assert lots.empty

def test_zero_shares_skipped() -> None:
    """Test that transactions with zero shares are skipped."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
    accounts.index.name = 'accountId'

    securities = pd.DataFrame([
        ['Test Security', 'XXX', 'ISIN123', None, False, 'EUR'],
    ], columns=['name', 'wkn', 'isin', 'note', 'isRetired', 'currency'], index=['sec-1'])
    securities.index.name = 'securityId'

    transactions = pd.DataFrame([
        [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 0.0, AccountType.SECURITIES.value, 'EUR', 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=securities, prices=None)

    lots = calculate_purchase_lots(portfolio, 'sec-1')

    assert lots.empty
