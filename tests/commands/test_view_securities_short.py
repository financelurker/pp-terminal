"""
    Regression tests for short positions (e.g. written/short options).

    Background: a short position has a negative net share count. The portfolio
    snapshot previously dropped any non-positive net position (`shares > 0`),
    so shorts disappeared entirely and `view securities --in-stock` never
    listed them. These tests lock in that:
      * the snapshot keeps a short with its negative quantity,
      * a flat (net zero) position stays excluded,
      * `view securities --in-stock` lists the short.
"""
# pylint: disable=duplicate-code

from datetime import datetime
from unittest.mock import Mock

import pandas as pd
import pytest
from typer import Context

from pp_terminal.commands.view_securities import print_securities
from pp_terminal.output.strategy import RichOutputStrategy
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.schemas import AccountType, TransactionType


@pytest.fixture(name='short_portfolio')
def provide_short_portfolio() -> Portfolio:
    """Portfolio with a long, a short (written put) and a flat position."""

    accounts = pd.DataFrame([
        ['Depot1', AccountType.SECURITIES.value, 'account1', False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['depot1'])
    accounts.index.name = 'accountId'

    securities = pd.DataFrame([
        ['MSCI World ETF', 'IE00B4L5Y983', 'EUR'],          # long
        ['Put DAX 18000 Dec25', 'OPT001', 'EUR'],           # short (written)
        ['Closed Position', 'FLAT01', 'EUR'],               # flat / net zero
    ], columns=['name', 'wkn', 'currency'], index=['sec1', 'opt1', 'flat1'])
    securities.index.name = 'securityId'

    transactions = pd.DataFrame([
        # long: net +70
        [datetime(2022, 1, 15), 'depot1', 'sec1', TransactionType.BUY.value, 5000.0, 50.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
        [datetime(2023, 6, 10), 'depot1', 'sec1', TransactionType.BUY.value, 7000.0, 30.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
        [datetime(2024, 1, 5), 'depot1', 'sec1', TransactionType.SELL.value, 2000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
        # short: written put, sold-to-open 2 contracts, no inbound -> net -2
        [datetime(2024, 3, 1), 'depot1', 'opt1', TransactionType.SELL.value, 600.0, 2.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
        # flat: buy 10, sell 10 -> net 0
        [datetime(2023, 2, 1), 'depot1', 'flat1', TransactionType.BUY.value, 1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
        [datetime(2023, 9, 1), 'depot1', 'flat1', TransactionType.SELL.value, 1100.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes', 'fees'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    prices = pd.DataFrame([
        [datetime(2024, 12, 31), 'sec1', 100.0],
        [datetime(2024, 12, 31), 'opt1', 30.0],
        [datetime(2024, 12, 31), 'flat1', 50.0],
    ], columns=['date', 'securityId', 'price'])
    prices = prices.set_index(['date', 'securityId'])

    portfolio = Portfolio(accounts, transactions, securities, prices)
    portfolio.base_currency = 'EUR'
    return portfolio


def test_snapshot_keeps_short_position(short_portfolio: Portfolio) -> None:
    """A short (net negative) position must survive in the snapshot with its sign."""
    snapshot = PortfolioSnapshot(short_portfolio, datetime(2024, 12, 31))
    shares = snapshot.shares.groupby('securityId').sum()

    assert shares.loc['sec1'] == pytest.approx(70.0)   # long unchanged
    assert shares.loc['opt1'] == pytest.approx(-2.0)   # short kept, negative
    assert 'flat1' not in shares.index                 # net zero stays excluded


def test_short_listed_with_in_stock(short_portfolio: Portfolio, capsys: pytest.CaptureFixture[str]) -> None:
    """`view securities --in-stock` must list the short and still hide the flat one."""
    ctx = Context(Mock())
    ctx.obj = Mock()
    ctx.obj.portfolio = short_portfolio
    ctx.obj.output = RichOutputStrategy()
    ctx.obj.config = {}

    print_securities(ctx, by=datetime(2024, 12, 31), in_stock=True)

    output = capsys.readouterr().out

    assert 'MSCI World ETF' in output       # long shown
    assert 'Put DAX 18000' in output         # short shown (was hidden before the fix)
    assert 'Closed Position' not in output   # flat / net zero filtered out

