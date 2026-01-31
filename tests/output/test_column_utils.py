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

import pytest

from pp_terminal.output.column_utils import normalize_columns
from pp_terminal.exceptions import InputError


@pytest.mark.parametrize(
    "requested",
    [
        ['Name', 'Balance', 'Type'],
        ['NAME', 'balance', 'TyPe'],
        [' Name ', '  Balance', 'Type  '],
        ['Name', 'Balance', 'Name', 'Type', 'Balance'],
    ],
    ids=['order_preservation', 'case_insensitive', 'whitespace_handling', 'duplicate_removal']
)
def test_normalize_columns_input_variations(requested: list[str]) -> None:
    """Test that column normalization handles various input formats correctly."""
    available = ['accountId', 'Name', 'Type', 'Balance']

    result = normalize_columns(requested, available)

    assert result == ['Name', 'Balance', 'Type']


def test_normalize_columns_with_uuid_attributes() -> None:
    """Test column normalization with UUID attribute columns."""
    uuid1 = '63c2f250-f5db-4ad1-a07d-f1abd742db5b'
    uuid2 = 'ffdeb0dd-8bd7-47b1-ac3f-30fedd6a47e0'

    requested = ['AccountId', 'Name', 'Balance', uuid1, uuid2]
    available = ['accountId', 'Name', 'Type', 'Balance', uuid1, uuid2]
    attributes = {
        uuid1: 'Custom Attribute 1',
        uuid2: 'Custom Attribute 2'
    }

    result = normalize_columns(requested, available, attributes)

    assert result == ['accountId', 'Name', 'Balance', uuid1, uuid2]


def test_normalize_columns_preserves_complex_order() -> None:
    """Test that complex ordering from config is preserved."""
    uuid1 = '63c2f250-f5db-4ad1-a07d-f1abd742db5b'
    uuid2 = 'ffdeb0dd-8bd7-47b1-ac3f-30fedd6a47e0'

    requested = ['AccountId', 'Name', 'Balance', uuid1, uuid2, 'Messages']
    available = ['accountId', 'Name', 'Type', 'Balance', 'Messages', uuid1, uuid2]

    result = normalize_columns(requested, available)

    assert result == ['accountId', 'Name', 'Balance', uuid1, uuid2, 'Messages']


def test_normalize_columns_invalid_column_without_attributes() -> None:
    """Test that invalid column raises InputError with available columns listed."""
    requested = ['Name', 'InvalidColumn', 'Balance']
    available = ['accountId', 'Name', 'Type', 'Balance']

    with pytest.raises(InputError) as exc_info:
        normalize_columns(requested, available)

    assert "Column 'InvalidColumn' not found" in str(exc_info.value)
    assert 'accountId' in str(exc_info.value)
    assert 'Name' in str(exc_info.value)


def test_normalize_columns_invalid_column_with_attributes() -> None:
    """Test that invalid column error includes friendly attribute names."""
    uuid1 = '63c2f250-f5db-4ad1-a07d-f1abd742db5b'

    requested = ['Name', 'InvalidColumn']
    available = ['accountId', 'Name', uuid1]
    attributes = {uuid1: 'Custom Attribute'}

    with pytest.raises(InputError) as exc_info:
        normalize_columns(requested, available, attributes)

    error_msg = str(exc_info.value)
    assert "Column 'InvalidColumn' not found" in error_msg
    assert 'Custom Attribute' in error_msg
    assert uuid1 in error_msg


def test_normalize_columns_empty_requested() -> None:
    """Test with empty requested columns list."""
    requested : list[str] = []
    available = ['accountId', 'Name', 'Balance']

    result = normalize_columns(requested, available)

    assert not result


def test_normalize_columns_empty_requested_with_currency() -> None:
    """Test that currency is included even with empty requested columns."""
    requested : list[str] = []
    available = ['accountId', 'Name', 'Balance', 'currency']

    result = normalize_columns(requested, available)

    assert result == ['currency']


def test_normalize_columns_only_currency_in_available() -> None:
    """Test when only currency column is available."""
    requested = ['Name', 'Balance']
    available = ['currency']

    with pytest.raises(InputError):
        normalize_columns(requested, available)


def test_normalize_columns_excludes_private_columns_from_error() -> None:
    """Test that columns starting with underscore are excluded from error messages."""
    requested = ['InvalidColumn']
    available = ['accountId', 'Name', '_internal', '_private']

    with pytest.raises(InputError) as exc_info:
        normalize_columns(requested, available)

    error_msg = str(exc_info.value)
    assert '_internal' not in error_msg
    assert '_private' not in error_msg
    assert 'accountId' in error_msg


def test_normalize_columns_real_world_accounts_config() -> None:
    """Test with real-world accounts view configuration."""
    requested = [
        'AccountId',
        'Name',
        'Balance',
        '63c2f250-f5db-4ad1-a07d-f1abd742db5b',
        'ffdeb0dd-8bd7-47b1-ac3f-30fedd6a47e0',
        'Messages'
    ]
    available = [
        'accountId',
        'Name',
        'Type',
        'Balance',
        'currency',
        '63c2f250-f5db-4ad1-a07d-f1abd742db5b',
        'ffdeb0dd-8bd7-47b1-ac3f-30fedd6a47e0',
        'Messages'
    ]

    result = normalize_columns(requested, available)

    # Currency should be first, then order should match requested
    assert result[0] == 'currency'
    assert result[1] == 'accountId'
    assert result[2] == 'Name'
    assert result[3] == 'Balance'
    assert result[-1] == 'Messages'


def test_normalize_columns_real_world_securities_config() -> None:
    """Test with real-world securities view configuration."""
    requested = [
        'SecurityId',
        'WKN',
        'Name',
        'Shares',
        'costBasis',
        'b3c38686-2d22-4b5d-8e38-e61dcf6fdde3',
        'Messages'
    ]
    available = [
        'securityId',
        'name',
        'wkn',
        'isin',
        'currency',
        'shares',
        'costBasis',
        'b3c38686-2d22-4b5d-8e38-e61dcf6fdde3',
        'Messages'
    ]

    result = normalize_columns(requested, available)

    # Currency should be first
    assert result[0] == 'currency'
    # Then the requested order (case-normalized)
    assert result[1] == 'securityId'
    assert result[2] == 'wkn'
    assert result[3] == 'name'
    assert result[4] == 'shares'
    assert result[5] == 'costBasis'
