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
from _pytest.fixtures import TopRequest
from pandas.testing import assert_frame_equal

from pp_terminal.commands.simulate_interest import calculate_interest
from pp_terminal.portfolio import Portfolio
from pp_terminal.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.pp_portfolio_builder import PpPortfolioBuilder


def test_empty_portfolio() -> None:
    portfolio = Portfolio()
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2022, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2022, 12, 31))

    result = calculate_interest(snapshot_begin, snapshot_end, 2.3)

    assert result is None


def test_no_deposit_accounts(sample_accounts: pd.DataFrame, sample_transactions: pd.DataFrame) -> None:
    portfolio = Portfolio(accounts=sample_accounts, transactions=sample_transactions)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2022, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2022, 12, 31))

    result = calculate_interest(snapshot_begin, snapshot_end, 2.3)

    expected_df = pd.DataFrame([
    ], columns=['Name', 'currency', 'mean_balance', 'interest', 'actual_interest'], index=pd.MultiIndex.from_tuples([
    ], names=['account_id', 'currency']))

    assert result is not None
    assert_frame_equal(expected_df, result, check_dtype=False)


def test_calculate_interest(sample_accounts: pd.DataFrame, sample_transactions: pd.DataFrame) -> None:
    portfolio = Portfolio(accounts=sample_accounts, transactions=sample_transactions)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2022, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2022, 12, 31))

    result = calculate_interest(snapshot_begin, snapshot_end, 2.3)

    expected_df = pd.DataFrame([
    ], columns=['Name', 'currency', 'mean_balance', 'interest', 'actual_interest'], index=pd.MultiIndex.from_tuples([

    ], names=['account_id', 'currency']))

    assert result is not None
    assert_frame_equal(expected_df, result, check_dtype=False)


def test_kommer(request: TopRequest) -> None:
    portfolio = PpPortfolioBuilder().construct(request.path.parent.parent / 'fixtures' / 'kommer.ids.xml')
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2021, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2021, 12, 31))

    expected_df = pd.DataFrame([
        ['Wertpapierkonto', 'EUR', 339.54724, 13.46723, None],
    ], columns=['Name', 'currency', 'mean_balance', 'interest', 'actual_interest'], index=pd.MultiIndex.from_tuples([
        ('e068fb14-2554-427e-b2d0-30dcc6e15717', 'EUR')
    ], names=['account_id', 'currency']))

    result = calculate_interest(snapshot_begin, snapshot_end, 3.75)

    assert result is not None
    assert_frame_equal(expected_df, result, check_dtype=False)


def test_empty_file(request: TopRequest) -> None:
    portfolio = PpPortfolioBuilder().construct(request.path.parent.parent / 'fixtures' / 'empty.ids.xml')
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2021, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2021, 12, 31))

    expected_df = pd.DataFrame([], columns=['Name', 'currency', 'mean_balance', 'interest', 'actual_interest'], index=pd.MultiIndex.from_tuples([], names=['account_id', 'currency']))

    result = calculate_interest(snapshot_begin, snapshot_end, 0.03)

    assert result is not None
    assert_frame_equal(expected_df, result, check_dtype=False)
