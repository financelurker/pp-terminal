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
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
import typer

from pp_terminal.commands.validate import validate_accounts
from pp_terminal.portfolio import Portfolio
from pp_terminal.schemas import AccountType


@pytest.fixture(name='sample_portfolio_with_limits')
def provide_sample_portfolio_with_limits() -> Portfolio:
    """Create a portfolio with deposit accounts for testing."""
    # Account metadata - Portfolio takes unified accounts DataFrame
    accounts = pd.DataFrame([
        ['Checking Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
        ['Savings Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
        ['Multi-Currency Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
        ['Retired Account', AccountType.DEPOSIT.value, None, True, 'EUR'],
    ], columns=['Name', 'Type', 'Referenceaccount_id', 'is_retired', 'currency'],
       index=['account-1', 'account-2', 'account-3', 'account-retired'])
    accounts.index.name = 'account_id'

    # Transactions for deposit accounts - Portfolio takes unified transactions DataFrame
    transactions = pd.DataFrame([
        [datetime(2025, 1, 1), 'account-1', None, 'DEPOSIT', 1050.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 2), 'account-2', None, 'DEPOSIT', 850.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 3), 'account-3', None, 'DEPOSIT', 500.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 4), 'account-3', None, 'DEPOSIT', 300.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 5), 'account-retired', None, 'DEPOSIT', 2000.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
    ], columns=['date', 'account_id', 'SecurityId', 'Type', 'amount', 'Shares', 'account_type', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'account_id', 'SecurityId'])

    return Portfolio(
        accounts=accounts,
        transactions=transactions,
        securities=None,
        prices=None
    )


@pytest.fixture(name='sample_portfolio_multi_currency')
def provide_sample_portfolio_multi_currency() -> Portfolio:
    """Create a portfolio with multi-currency balances."""
    accounts = pd.DataFrame([
        ['Multi-Currency Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
    ], columns=['Name', 'Type', 'Referenceaccount_id', 'is_retired', 'currency'],
       index=['account-multi'])
    accounts.index.name = 'account_id'

    # Transactions in multiple currencies
    transactions = pd.DataFrame([
        [datetime(2025, 1, 1), 'account-multi', None, 'DEPOSIT', 500.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 2), 'account-multi', None, 'DEPOSIT', 300.0, 0.0, AccountType.DEPOSIT.value, 'USD', 0.0],
        [datetime(2025, 1, 3), 'account-multi', None, 'DEPOSIT', 200.0, 0.0, AccountType.DEPOSIT.value, 'GBP', 0.0],
    ], columns=['date', 'account_id', 'SecurityId', 'Type', 'amount', 'Shares', 'account_type', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'account_id', 'SecurityId'])

    return Portfolio(
        accounts=accounts,
        transactions=transactions,
        securities=None,
        prices=None
    )


def test_account_below_limit(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that no errors are issued when balance is below limit."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {'account-2': 1000.0}}}  # Balance is 850, limit is 1000
    )

    # Should complete successfully without raising any exception
    validate_accounts(ctx)


def test_account_at_limit(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that no error when balance equals limit."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {'account-2': 850.0}}}  # Balance is 850, limit is 850
    )

    # Should complete successfully without raising any exception
    validate_accounts(ctx)


def test_account_above_limit(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that typer.Exit is raised when balance exceeds limit."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {'account-1': 1000.0}}}  # Balance is 1050, limit is 1000
    )

    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_no_configured_limits(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that validation completes successfully when no limits are configured."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {}}}
    )

    # Should complete successfully without raising any exception
    validate_accounts(ctx)


def test_no_limits_key_in_config(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that validation completes successfully when limits key is missing from config."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={}
    )

    # Should complete successfully without raising any exception
    validate_accounts(ctx)


def test_account_without_limit(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that accounts without configured limits are skipped."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {'account-1': 1000.0}}}  # Only account-1 has a limit
    )

    # Should raise error because account-1 (balance 1050) exceeds limit 1000
    # account-2 has no limit so should be ignored
    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_retired_account(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that retired accounts are skipped even if they have limits."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {'account-retired': 1000.0}}}  # Retired account has limit
    )

    # Should complete successfully - retired account is ignored
    validate_accounts(ctx)


def test_multi_currency_sum(sample_portfolio_multi_currency: Portfolio) -> None:
    """Test that balances are correctly summed across multiple currencies."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_multi_currency,
        config={'limits': {'accounts': {'account-multi': 900.0}}}  # Total is 500+300+200=1000
    )

    # Should raise error because total balance (1000) > limit (900)
    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_empty_balances() -> None:
    """Test that validation completes successfully when no balances are found."""
    empty_accounts = pd.DataFrame([], columns=['Name', 'Type', 'Referenceaccount_id', 'is_retired', 'currency'])
    empty_accounts.index.name = 'account_id'

    empty_portfolio = Portfolio(
        accounts=empty_accounts,
        transactions=None,
        securities=None,
        prices=None
    )

    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=empty_portfolio,
        config={'limits': {'accounts': {'account-1': 1000.0}}}
    )

    # Should complete successfully without raising any exception
    validate_accounts(ctx)


def test_no_deposit_accounts() -> None:
    """Test that validation completes successfully when deposit_accounts is None."""
    empty_portfolio = Portfolio(
        accounts=None,
        transactions=None,
        securities=None,
        prices=None
    )

    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=empty_portfolio,
        config={'limits': {'accounts': {'account-1': 1000.0}}}
    )

    # Should complete successfully without raising any exception
    validate_accounts(ctx)


def test_multiple_accounts_mixed_status(sample_portfolio_with_limits: Portfolio) -> None:
    """Test validation with multiple accounts having different statuses."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {
            'account-1': 1000.0,  # Balance 1050 - should ERROR
            'account-2': 1000.0,  # Balance 850 - OK
            'account-3': 700.0,   # Balance 800 - should ERROR
        }}}
    )

    # Should raise error because account-1 and account-3 exceed their limits
    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_default_limit_only(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that default limit applies to all accounts."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {
            'default': 1000.0  # Balance: account-1=1050, account-2=850, account-3=800
        }}}
    )

    # Should raise error because account-1 (1050) exceeds default limit (1000)
    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_default_limit_with_specific_override(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that specific limits override the default limit."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {
            'default': 800.0,      # Would fail account-2 (850) and account-1 (1050)
            'account-2': 900.0,    # Override: account-2 should pass (850 < 900)
        }}}
    )

    # Should raise error because account-1 (1050) and account-3 (800) exceed default limit (800)
    # account-2 passes because specific limit (900) > balance (850)
    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_default_limit_all_pass(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that all accounts pass when default limit is high enough."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {
            'default': 2000.0  # All balances below this
        }}}
    )

    # Should complete successfully - all accounts within limit
    validate_accounts(ctx)


def test_default_limit_with_no_specific_limits(sample_portfolio_with_limits: Portfolio) -> None:
    """Test default limit applies when no specific limits are configured."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {
            'default': 825.0  # Will fail account-2 (850) and account-1 (1050)
        }}}
    )

    # Should raise error
    with pytest.raises(typer.Exit) as exc_info:
        validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_mixed_default_and_specific_limits(sample_portfolio_with_limits: Portfolio) -> None:
    """Test combination of default limit and multiple specific limits."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'limits': {'accounts': {
            'default': 1000.0,     # Applies to account-2 (850) and account-3 (800)
            'account-1': 1100.0,   # Specific override for account-1 (1050)
        }}}
    )

    # All accounts should pass:
    # - account-1: 1050 <= 1100 (specific)
    # - account-2: 850 <= 1000 (default)
    # - account-3: 800 <= 1000 (default)
    validate_accounts(ctx)
