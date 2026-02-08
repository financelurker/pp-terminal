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

from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.schemas import AccountType
from pp_terminal.domain.vap import calculate_base_yield_per_share


@pytest.fixture(name='minimal_accounts')
def provide_minimal_accounts() -> pd.DataFrame:
    accounts = pd.DataFrame([
        ['Test Account', AccountType.SECURITIES.value, 'EUR', None]
    ], columns=['name', 'type', 'currency', 'referenceAccount'], index=['acc-1'])
    accounts.index.name = 'accountId'
    return accounts


@pytest.fixture(name='minimal_securities')
def provide_minimal_securities() -> pd.DataFrame:
    securities = pd.DataFrame([
        ['Security 1', 'WKN1', 'EUR']
    ], columns=['name', 'wkn', 'currency'], index=['sec-1'])
    securities.index.name = 'securityId'
    return securities


def test_outcome_less_than_base_yield(minimal_accounts: pd.DataFrame, minimal_securities: pd.DataFrame) -> None:
    prices = pd.DataFrame([
        [datetime(2024, 1, 1), 'sec-1', 100.0],
        [datetime(2024, 12, 31), 'sec-1', 101.0],
    ], columns=['date', 'securityId', 'price']).set_index(['date', 'securityId'])

    portfolio = Portfolio(
        minimal_accounts,
        None,
        minimal_securities,
        prices
    )

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate_base_yield_per_share(snapshot_begin, snapshot_end, 2.29)

    # outcome = 101 - 100 = 1.0
    # base_yield = 100 * 0.7 * 2.29 / 100 = 1.603
    # min(1.0, 1.603) = 1.0
    assert result['sec-1'] == pytest.approx(1.0)


def test_outcome_greater_than_base_yield(minimal_accounts: pd.DataFrame, minimal_securities: pd.DataFrame) -> None:
    prices = pd.DataFrame([
        [datetime(2024, 1, 1), 'sec-1', 100.0],
        [datetime(2024, 12, 31), 'sec-1', 120.0],
    ], columns=['date', 'securityId', 'price']).set_index(['date', 'securityId'])

    portfolio = Portfolio(
        minimal_accounts,
        None,
        minimal_securities,
        prices
    )

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate_base_yield_per_share(snapshot_begin, snapshot_end, 2.29)

    # outcome = 120 - 100 = 20.0
    # base_yield = 100 * 0.7 * 2.29 / 100 = 1.603
    # min(20.0, 1.603) = 1.603
    assert result['sec-1'] == pytest.approx(1.603)


def test_negative_base_rate(minimal_accounts: pd.DataFrame, minimal_securities: pd.DataFrame) -> None:
    prices = pd.DataFrame([
        [datetime(2024, 1, 1), 'sec-1', 100.0],
        [datetime(2024, 12, 31), 'sec-1', 105.0],
    ], columns=['date', 'securityId', 'price']).set_index(['date', 'securityId'])

    portfolio = Portfolio(
        minimal_accounts,
        None,
        minimal_securities,
        prices
    )

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate_base_yield_per_share(snapshot_begin, snapshot_end, -0.45)

    # outcome = 105 - 100 = 5.0
    # base_yield = 100 * 0.7 * max(-0.45, 0) / 100 = 0
    # min(5.0, 0) = 0
    assert result['sec-1'] == pytest.approx(0.0)


def test_price_decrease(minimal_accounts: pd.DataFrame, minimal_securities: pd.DataFrame) -> None:
    prices = pd.DataFrame([
        [datetime(2024, 1, 1), 'sec-1', 100.0],
        [datetime(2024, 12, 31), 'sec-1', 90.0],
    ], columns=['date', 'securityId', 'price']).set_index(['date', 'securityId'])

    portfolio = Portfolio(
        minimal_accounts,
        None,
        minimal_securities,
        prices
    )

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate_base_yield_per_share(snapshot_begin, snapshot_end, 2.29)

    # outcome = max(90 - 100, 0) = 0
    # base_yield = 100 * 0.7 * 2.29 / 100 = 1.603
    # min(0, 1.603) = 0
    assert result['sec-1'] == pytest.approx(0.0)


def test_zero_base_rate(minimal_accounts: pd.DataFrame, minimal_securities: pd.DataFrame) -> None:
    prices = pd.DataFrame([
        [datetime(2024, 1, 1), 'sec-1', 100.0],
        [datetime(2024, 12, 31), 'sec-1', 110.0],
    ], columns=['date', 'securityId', 'price']).set_index(['date', 'securityId'])

    portfolio = Portfolio(
        minimal_accounts,
        None,
        minimal_securities,
        prices
    )

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    result = calculate_base_yield_per_share(snapshot_begin, snapshot_end, 0.0)

    # outcome = 110 - 100 = 10.0
    # base_yield = 100 * 0.7 * 0.0 / 100 = 0
    # min(10.0, 0) = 0
    assert result['sec-1'] == pytest.approx(0.0)
