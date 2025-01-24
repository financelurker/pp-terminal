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
from datetime import datetime

import pandas as pd
from _pytest.fixtures import TopRequest
from _pytest.monkeypatch import MonkeyPatch
from pandas.testing import assert_frame_equal
import pytest

from pp_terminal.portfolio_service import PortfolioService
from pp_terminal.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.schemas import TransactionType, AccountType
from pp_terminal.commands.simulate_vorabpauschale import calculate
from pp_terminal.pp_portfolio_service_adapter import PortfolioPerformanceService


@pytest.fixture(name='sample_depots')
def provide_sample_depots() -> pd.DataFrame:
    depots = pd.DataFrame([['Testdepot', AccountType.DEPOT.value]], columns=['Name', 'Type'], index=['1'])
    depots.index.name = 'AccountId'

    return depots


@pytest.fixture(name='sample_securities')
def provide_sample_securities() -> pd.DataFrame:
    securities = pd.DataFrame([['Some Share', 'A23432']], columns=['Name', 'Wkn'], index=['1234567890'])
    securities.index.name = 'SecurityId'

    return securities


@pytest.fixture(name='sample_prices')
def provide_sample_prices() -> pd.DataFrame:
    return (pd.DataFrame([
        [datetime(2017, 12, 30), '1234567890', 200.0],
        [datetime(2018, 1, 10), '1234567890', 246.66],
    ], columns=['Date', 'SecurityId', 'Price'])
            .set_index(['Date', 'SecurityId']))


@pytest.fixture(name='sample_transactions')
def provide_sample_transactions() -> pd.DataFrame:
    return (pd.DataFrame([[datetime(2018, 8, 15), TransactionType.BUY.value, 1000.0, 5.0, '1234567890', '1', AccountType.DEPOT.value]], columns=['Date', 'Type', 'amount', 'Shares', 'SecurityId', 'AccountId', 'account_type'])
            .set_index(['Date', 'SecurityId', 'AccountId']))


def test_calculate_empty_if_no_depots(sample_depots: pd.DataFrame, sample_securities: pd.DataFrame, sample_prices: pd.DataFrame) -> None:
    transactions = (pd.DataFrame([[datetime(2018, 8, 15), TransactionType.BUY.value, 1000.0, 5.0, '1234567890', '1', AccountType.DEPOT.value]], columns=['Date', 'Type', 'amount', 'Shares', 'SecurityId', 'AccountId', 'account_type'])
                    .set_index(['Date', 'SecurityId', 'AccountId']))

    # drop all rows
    sample_depots = sample_depots.drop(sample_depots.index)
    sample_securities = sample_securities.drop(sample_securities.index)
    sample_prices = sample_prices.drop(sample_prices.index)
    transactions = transactions.drop(transactions.index)

    portfolio = PortfolioService(sample_depots, transactions, sample_securities, sample_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2022, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2022, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375)

    assert result is None


def test_calculate_empty_if_no_security_prices(sample_depots: pd.DataFrame, sample_transactions: pd.DataFrame, sample_securities: pd.DataFrame, sample_prices: pd.DataFrame) -> None:
    sample_prices = sample_prices.drop(sample_prices.index)
    sample_transactions = sample_transactions.drop(sample_transactions.index)

    portfolio = PortfolioService(sample_depots, sample_transactions, sample_securities, sample_prices)

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2022, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2022, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375)

    assert result is None


def test_inyear_buy(sample_depots: pd.DataFrame, sample_transactions: pd.DataFrame, sample_securities: pd.DataFrame, sample_prices: pd.DataFrame) -> None:
    portfolio = PortfolioService(sample_depots, sample_transactions, sample_securities, sample_prices)
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2018, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2018, 12, 31))

    expected_df = pd.DataFrame([['A23432', 'Some Share', 1.76]], columns=['Wkn', 'Name', 'Testdepot'], index=['1234567890'])
    expected_df.index.name = 'SecurityId'

    result = calculate(snapshot_begin, snapshot_end, 2.29, 26.375)

    assert result is not None
    assert_frame_equal(expected_df, result.round(2))

# @todo test with sell

# @see https://github.com/MStrecke/vorabpauschale/blob/master/test.ini
# @see https://www.justetf.com/de/news/etf/etf-und-steuern-das-neue-investmentsteuergesetz-ab-2018.html
samples = [
    (0.0, 0, 10000, 10300, 0),  # zero base rate
    (0.0, 0, 10000, 10300, -1.29),  # negative base rate
    (295.95, 0, 100000, 125000, 2.29),
    (0.0, 300, 10000, 9750, 2.29),  # justetf Steuer-Beispiel 1.1: Ausschüttender ETF mit kleinem Gewinn
    (0.0, 0, 10000, 9750, 2.29),  # justetf Steuer-Beispiel 1.1 mit Verlust ohne Ausschüttung
    (9.23, 0, 10000, 10050, 2.29),  # justetf Steuer-Beispiel 1.2: Thesaurierender ETF mit kleinem Gewinn
    (0.0, 300, 10000, 10700, 2.29),  # justetf Steuer-Beispiel 2.1: Ausschüttender ETF mit hohem Gewinn
    (29.60, 0, 10000, 11000, 2.29),  # justetf Steuer-Beispiel 2.2: Thesaurierender ETF mit hohem Gewinn
    (14.22, 0, 10000, 10700, 1.1)
]


@pytest.mark.parametrize("expected_tax_value, payout, value_begin, value_end, base_rate_percent", samples)
def test_single_security_buy_only(sample_depots: pd.DataFrame, sample_securities: pd.DataFrame, expected_tax_value: float, payout: float, value_begin: float, value_end: float, base_rate_percent: float) -> None:  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    share_price_begin = 50
    shares = value_begin/share_price_begin

    prices = pd.DataFrame([
        [datetime(2023, 12, 1), '1234567890', 46.54],
        [datetime(2023, 12, 5), '1234567890', share_price_begin],
        [datetime(2024, 2, 1), '1234567890', 52.01],
        [datetime(2024, 6, 1), '1234567890', 60.4222],
        [datetime(2024, 12, 31), '1234567890', value_end / shares],
        [datetime(2023, 12, 1), '1234567890', 46.54],
        [datetime(2025, 1, 2), '1234567890', 45.302],
    ], columns=['Date', 'SecurityId', 'Price']).set_index(['Date', 'SecurityId'])
    transactions = pd.DataFrame([
        [datetime(2023, 12, 6), TransactionType.BUY.value, float(value_begin), shares, '1234567890', '1', AccountType.DEPOT.value],
        [datetime(2024, 6, 4), TransactionType.DIVIDENDS.value, float(payout), shares, '1234567890', '1', AccountType.DEPOT.value],
    ], columns=['Date', 'Type', 'amount', 'Shares', 'SecurityId', 'AccountId', 'account_type']).set_index(['Date', 'SecurityId', 'AccountId'])

    portfolio = PortfolioService(sample_depots, transactions, sample_securities, prices)

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2024, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2024, 12, 31))

    expected_df = pd.DataFrame([['A23432', 'Some Share', expected_tax_value]], columns=['Wkn', 'Name', 'Testdepot'], index=['1234567890'])
    expected_df.index.name = 'SecurityId'

    result = calculate(snapshot_begin, snapshot_end, base_rate_percent, 26.375 * 0.7)

    if expected_tax_value == 0:
        assert result is None
    else:
        assert result is not None
        assert_frame_equal(expected_df, result.round(2))


def test_kommer(request: TopRequest, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr('ppxml2db.dbhelper.db', sqlite3.connect(':memory:'))
    portfolio = PortfolioPerformanceService(request.path.parent.parent / 'fixtures' / 'kommer.ids.xml')
    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2021, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2021, 12, 31))

    expected_df = pd.DataFrame([
        ['ETF013', 'Lyxor MSCI Pacific UCITS ETF', 1.44539],
        ['A0MZWQ', 'iShares Core MSCI Europe UCITS ETF EUR (Dist)', 3.88498],
        ['A2DK6R', 'iShares Diversified Commodity Swap UCITS ETF', 3.37515],
        ['A0HGWC', 'iShares MSCI EM UCITS ETF (Dist)', 6.73028],
        ['A0J201', 'iShares MSCI North America UCITS ETF', 5.84267],
        [None, 'Related Account Balance', 475.88]
    ], columns=['Wkn', 'Name', 'Depot'], index=[
        'ff0a2b77-9749-45b0-8333-cb1d9787812c',
        'c770a389-0a84-442c-ad85-2a58c3066924',
        '97000a3b-0a3d-4779-ad6c-1234bfea5e72',
        '47094920-535c-4508-9a92-80c01933f567',
        'daab10fd-c3fb-4430-a368-0ce0cdf551c8',
        5,
    ])
    expected_df.index.name = 'SecurityId'

    result = calculate(snapshot_begin, snapshot_end, 2.0, 26.375)

    assert_frame_equal(expected_df, result)


def test_empty_file(request: TopRequest, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr('ppxml2db.dbhelper.db', sqlite3.connect(':memory:'))
    portfolio = PortfolioPerformanceService(request.path.parent.parent / 'fixtures' / 'empty.ids.xml')

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(2021, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(2021, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, 2.0, 26.375)

    assert result is None
