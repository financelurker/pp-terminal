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

import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pandas as pd
import pytest
import typer

from pp_terminal.commands.validate import log_validate_accounts
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType


@pytest.fixture(name='sample_portfolio_with_limits')
def provide_sample_portfolio_with_limits() -> Portfolio:
    """Create a portfolio with deposit accounts for testing."""
    accounts = pd.DataFrame([
        ['Checking Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
        ['Savings Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
        ['Multi-Currency Account', AccountType.DEPOSIT.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['account-1', 'account-2', 'account-3'])
    accounts.index.name = 'accountId'

    transactions = pd.DataFrame([
        [datetime(2025, 1, 1), 'account-1', None, 'DEPOSIT', 1050.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 2), 'account-2', None, 'DEPOSIT', 850.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
        [datetime(2025, 1, 3), 'account-3', None, 'DEPOSIT', 800.0, 0.0, AccountType.DEPOSIT.value, 'EUR', 0.0],
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    return Portfolio(
        accounts=accounts,
        transactions=transactions,
        securities=None,
        prices=None
    )


def test_no_validation_config(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that validation completes successfully when no validation config exists."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={}
    )
    log_validate_accounts(ctx)


def test_balance_limit_pass(sample_portfolio_with_limits: Portfolio) -> None:
    """Test balance limit validation when all accounts pass."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'commands': {'validate': {'accounts': {'rules': [
            {'type': 'balance-limit', 'value': 2000.0}
        ]}}}}
    )
    log_validate_accounts(ctx)


def test_balance_limit_fail(sample_portfolio_with_limits: Portfolio) -> None:
    """Test balance limit validation when account exceeds limit."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'commands': {'validate': {'accounts': {'rules': [
            {'type': 'balance-limit', 'value': 1000.0}
        ]}}}}
    )

    with pytest.raises(typer.Exit) as exc_info:
        log_validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_entity_specific_rule(sample_portfolio_with_limits: Portfolio) -> None:
    """Test entity-specific rules with applies-to."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'commands': {'validate': {'accounts': {'rules': [
            {'type': 'balance-limit', 'value': 900.0, 'applies-to': ['account-1']}
        ]}}}}
    )

    with pytest.raises(typer.Exit) as exc_info:
        log_validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_attribute_based_rule(sample_portfolio_with_limits: Portfolio) -> None:
    """Test balance-limit-from-attribute rule type."""
    test_attr_uuid = 'test-attr-uuid-12345'
    sample_portfolio_with_limits._accounts[test_attr_uuid] = pd.Series({  # pylint: disable=protected-access
        'account-1': 1000.0,
    })

    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={
            'commands': {'validate': {'accounts': {'rules': [
                {'type': 'balance-limit-from-attribute', 'value': test_attr_uuid}
            ]}}}
        }
    )

    with pytest.raises(typer.Exit) as exc_info:
        log_validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_warning_severity(sample_portfolio_with_limits: Portfolio) -> None:
    """Test that warning severity doesn't raise an error."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'commands': {'validate': {'accounts': {'rules': [
            {'type': 'balance-limit', 'value': 1000.0, 'severity': 'warning'}
        ]}}}}
    )
    log_validate_accounts(ctx)


def test_mixed_severities(sample_portfolio_with_limits: Portfolio) -> None:
    """Test mixed warning and error severities."""
    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'commands': {'validate': {'accounts': {'rules': [
            {'type': 'balance-limit', 'value': 900.0, 'severity': 'warning', 'applies-to': ['account-2']},
            {'type': 'balance-limit', 'value': 750.0, 'applies-to': ['account-3']}
        ]}}}}
    )

    with pytest.raises(typer.Exit) as exc_info:
        log_validate_accounts(ctx)

    assert exc_info.value.exit_code == 1


def test_multiple_errors_logged(sample_portfolio_with_limits: Portfolio, caplog: Any) -> None:
    """Test that all errors are logged before exiting."""
    caplog.set_level(logging.ERROR)

    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={'commands': {'validate': {'accounts': {'rules': [
            {'type': 'balance-limit', 'value': 800.0}
        ]}}}}
    )

    with pytest.raises(typer.Exit) as exc_info:
        log_validate_accounts(ctx)

    assert exc_info.value.exit_code == 1
    assert len(caplog.records) == 2
    assert 'account-1' in caplog.text
    assert 'account-2' in caplog.text
    assert '1050' in caplog.text
    assert '850' in caplog.text


def test_date_passed_with_friendly_name(sample_portfolio_with_limits: Portfolio, caplog: Any) -> None:
    """Test that date-passed-from-attribute shows friendly attribute name in message."""
    caplog.set_level(logging.ERROR)

    test_attr_uuid = 'test-date-attr-uuid-12345'
    sample_portfolio_with_limits._accounts[test_attr_uuid] = pd.Series({  # pylint: disable=protected-access
        'account-1': datetime(2020, 1, 1),
    })

    ctx = Mock()
    ctx.invoked_subcommand = None
    ctx.obj = SimpleNamespace(
        portfolio=sample_portfolio_with_limits,
        config={
            'commands': {'validate': {'accounts': {'rules': [
                {'type': 'date-passed-from-attribute', 'value': test_attr_uuid}
            ]}}}
        }
    )

    with pytest.raises(typer.Exit) as exc_info:
        log_validate_accounts(ctx)

    assert exc_info.value.exit_code == 1
    assert len(caplog.records) == 1
    assert 'date attribute has passed 2020-01-01' in caplog.text
