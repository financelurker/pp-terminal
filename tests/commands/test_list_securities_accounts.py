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

from pp_terminal.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.pp_portfolio_builder import PpPortfolioBuilder
from pp_terminal.commands.list_accounts import calculate_securities_accounts_sum


def test_kommer(request: TopRequest) -> None:
    portfolio = PpPortfolioBuilder().construct(request.path.parent.parent / 'fixtures' / 'kommer.ids.xml')

    expected_df = pd.DataFrame([
        ['Kryptowährung', 72.07],
        ['Depot', 3038.80],
        ['Depot', 14031.37],
    ], columns=['Name', 'Balance'], index=pd.MultiIndex.from_tuples([
        ('57ede399-7ef8-4696-a874-1f425e25d1f5', 'EUR'),
        ('dc6fac85-6c6e-47f1-a968-2b5b84d90997', 'USD'),
        ('dc6fac85-6c6e-47f1-a968-2b5b84d90997', 'EUR'),
    ], names=['account_id', 'currency']))

    result = calculate_securities_accounts_sum(PortfolioSnapshot(portfolio, datetime(2024, 1, 1)))[['Name', 'Balance']]

    assert_frame_equal(expected_df, result.round(2), check_names=False)


def test_empty_file(request: TopRequest) -> None:
    portfolio = PpPortfolioBuilder().construct(request.path.parent.parent / 'fixtures' / 'empty.ids.xml')

    expected_df = pd.DataFrame([], columns=['Name', 'Type', 'Balance'], index=pd.MultiIndex.from_tuples([], names=['account_id', 'currency']))
    expected_df.index.name = 'account_id'

    result = calculate_securities_accounts_sum(PortfolioSnapshot(portfolio))

    assert_frame_equal(expected_df, result, check_dtype=False)
