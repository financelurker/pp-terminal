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

import sqlite3

import pandas as pd
from _pytest.fixtures import TopRequest
from _pytest.monkeypatch import MonkeyPatch
from pandas.testing import assert_frame_equal

from pp_terminal.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.pp_portfolio_service_adapter import PortfolioPerformanceService
from pp_terminal.commands.view_deposit_accounts import calculate_sum


def test_calculate_sum(request: TopRequest, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr('ppxml2db.dbhelper.db', sqlite3.connect(':memory:'))
    portfolio = PortfolioPerformanceService(request.path.parent.parent / 'fixtures' / 'kommer.ids.xml')

    expected_df = pd.DataFrame([
        ['Tagesgeld', 'EUR', 500.0, None, None],
        ['Wertpapierkonto', 'EUR', 593.87, None, None],
        ['Fremdwährungskonto USD', 'USD', None, None, 324.0],
        ['Fremdwährungskonto GBP', 'GBP', None, 2000.0, None],
    ], columns=['Name', 'currency', 'EUR', 'GBP', 'USD'], index=[
        'ea9414e0-1787-46c0-92b3-8e2370eb892e',
        'e068fb14-2554-427e-b2d0-30dcc6e15717',
        '789294db-0aa4-4673-9d91-ad083c9d6916',
        'db94317b-26ed-4a8b-bf6c-2f535a217138',
    ])
    expected_df.index.name = 'AccountId'

    result = calculate_sum(PortfolioSnapshot(portfolio))

    assert_frame_equal(expected_df, result)


def test_empty_file(request: TopRequest, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr('ppxml2db.dbhelper.db', sqlite3.connect(':memory:'))
    portfolio = PortfolioPerformanceService(request.path.parent.parent / 'fixtures' / 'empty.ids.xml')

    expected_df = pd.DataFrame([], columns=['Name', 'currency'], index=[])
    expected_df.index.name = 'AccountId'

    result = calculate_sum(PortfolioSnapshot(portfolio))

    assert_frame_equal(expected_df, result)
