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

import pandas as pd
import numpy as np
import pytest
from _pytest.logging import LogCaptureFixture

from pp_terminal.attribute_type_converter import convert_attribute_types


def test_convert_percent_plain_converter() -> None:
    """Test PercentPlainConverter normalization (30 -> 0.3)."""
    attr_uuid = 'test-attr-uuid-001'
    df = pd.DataFrame({
        'Name': ['ETF A', 'ETF B', 'ETF C'],
        'Wkn': ['A1', 'B1', 'C1'],
        attr_uuid: ['30', '15', '100'],  # 30%, 15%, 100%
        f'{attr_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
        ]
    })

    attributes = {'test-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    assert result.loc[0, attr_uuid] == pytest.approx(0.30)
    assert result.loc[1, attr_uuid] == pytest.approx(0.15)
    assert result.loc[2, attr_uuid] == pytest.approx(1.0)
    assert f'{attr_uuid}_converter' not in result.columns


def test_convert_percent_converter() -> None:
    """Test PercentConverter normalization (0.3 -> 0.3)."""
    attr_uuid = 'test-attr-uuid-002'
    df = pd.DataFrame({
        'Name': ['ETF A', 'ETF B', 'ETF C'],
        'Wkn': ['A1', 'B1', 'C1'],
        attr_uuid: ['0.3', '0.15', '1.0'],  # 30%, 15%, 100%
        f'{attr_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentConverter',
        ]
    })

    attributes = {'test-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    assert result.loc[0, attr_uuid] == pytest.approx(0.30)
    assert result.loc[1, attr_uuid] == pytest.approx(0.15)
    assert result.loc[2, attr_uuid] == pytest.approx(1.0)
    assert f'{attr_uuid}_converter' not in result.columns


def test_convert_date_converter() -> None:
    """Test DateConverter conversion."""
    attr_uuid = 'test-attr-uuid-003'
    df = pd.DataFrame({
        'Name': ['Account A', 'Account B'],
        attr_uuid: ['2025-12-31', '2026-01-15'],
        f'{attr_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$DateConverter',
            'name.abuchen.portfolio.model.AttributeType$DateConverter',
        ]
    })

    attributes = {'test-date-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    assert pd.Timestamp(result.loc[0, attr_uuid]) == pd.Timestamp('2025-12-31')
    assert pd.Timestamp(result.loc[1, attr_uuid]) == pd.Timestamp('2026-01-15')
    assert f'{attr_uuid}_converter' not in result.columns


def test_convert_long_converter() -> None:
    """Test LongConverter conversion."""
    attr_uuid = 'test-attr-uuid-004'
    df = pd.DataFrame({
        'Name': ['Item A', 'Item B'],
        attr_uuid: ['100000', '250000'],
        f'{attr_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$LongConverter',
            'name.abuchen.portfolio.model.AttributeType$LongConverter',
        ]
    })

    attributes = {'test-long-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    assert result.loc[0, attr_uuid] == pytest.approx(100000.0)
    assert result.loc[1, attr_uuid] == pytest.approx(250000.0)
    assert f'{attr_uuid}_converter' not in result.columns


def test_convert_string_converter() -> None:
    """Test StringConverter (keeps as-is)."""
    attr_uuid = 'test-attr-uuid-005'
    df = pd.DataFrame({
        'Name': ['Item A', 'Item B'],
        attr_uuid: ['Value 1', 'Value 2'],
        f'{attr_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$StringConverter',
            'name.abuchen.portfolio.model.AttributeType$StringConverter',
        ]
    })

    attributes = {'test-string-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    assert result.loc[0, attr_uuid] == 'Value 1'
    assert result.loc[1, attr_uuid] == 'Value 2'
    assert f'{attr_uuid}_converter' not in result.columns


def test_convert_unknown_converter(caplog: LogCaptureFixture) -> None:
    """Test handling of unknown converter type (keeps raw value with warning)."""
    attr_uuid = 'test-attr-uuid-006'
    df = pd.DataFrame({
        'Name': ['ETF Unknown'],
        'Wkn': ['UNK1'],
        attr_uuid: ['30'],
        f'{attr_uuid}_converter': ['some.unknown.Converter'],
    })

    attributes = {'test-unknown-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    # Unknown converter should keep raw value
    assert result.loc[0, attr_uuid] == '30'
    assert f"Unknown converter type 'some.unknown.Converter' for attribute 'test-unknown-attr' ({attr_uuid}). Keeping raw value." in caplog.text


def test_convert_invalid_format(caplog: LogCaptureFixture) -> None:
    """Test handling of unparseable values."""
    attr_uuid = 'test-attr-uuid-007'
    df = pd.DataFrame({
        'Name': ['ETF Invalid'],
        'Wkn': ['INV1'],
        attr_uuid: ['invalid'],
        f'{attr_uuid}_converter': ['name.abuchen.portfolio.model.AttributeType$PercentPlainConverter'],
    })

    attributes = {'test-invalid-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    # Invalid format should be set to NaN
    assert pd.isna(result.loc[0, attr_uuid])
    assert f"Failed to parse attribute 'test-invalid-attr' ({attr_uuid}) value 'invalid'" in caplog.text


def test_convert_missing_values(caplog: LogCaptureFixture) -> None:
    """Test handling of missing attribute or converter values."""
    attr_uuid = 'test-attr-uuid-008'
    df = pd.DataFrame({
        'Name': ['Item No Value', 'Item No Converter', 'Item Both Missing'],
        attr_uuid: [np.nan, '30', np.nan],
        f'{attr_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            np.nan,
            np.nan,
        ]
    })

    attributes = {'test-missing-attr': attr_uuid}
    result = convert_attribute_types(df, attributes)

    # All should remain NaN
    assert pd.isna(result.loc[0, attr_uuid])  # No value -> stays NaN
    assert pd.isna(result.loc[1, attr_uuid])  # No converter -> set to NaN with warning
    assert pd.isna(result.loc[2, attr_uuid])  # Both missing -> stays NaN
    assert f'{attr_uuid}_converter' not in result.columns

    # Warning should be logged for missing converter
    assert f"Missing converter type for attribute 'test-missing-attr' ({attr_uuid})" in caplog.text


def test_convert_multiple_attributes() -> None:
    """Test converting multiple attributes at once."""
    attr1_uuid = 'attr-uuid-001'
    attr2_uuid = 'attr-uuid-002'

    df = pd.DataFrame({
        'Name': ['ETF A', 'ETF B'],
        'Wkn': ['A1', 'B1'],
        attr1_uuid: ['30', '15'],
        f'{attr1_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
        ],
        attr2_uuid: ['2025-12-31', '2026-01-15'],
        f'{attr2_uuid}_converter': [
            'name.abuchen.portfolio.model.AttributeType$DateConverter',
            'name.abuchen.portfolio.model.AttributeType$DateConverter',
        ]
    })

    attributes = {
        'exemption-rate': attr1_uuid,
        'valid-until': attr2_uuid
    }
    result = convert_attribute_types(df, attributes)

    # Check first attribute (percent)
    assert result.loc[0, attr1_uuid] == pytest.approx(0.30)
    assert result.loc[1, attr1_uuid] == pytest.approx(0.15)

    # Check second attribute (date)
    assert pd.Timestamp(result.loc[0, attr2_uuid]) == pd.Timestamp('2025-12-31')
    assert pd.Timestamp(result.loc[1, attr2_uuid]) == pd.Timestamp('2026-01-15')

    # Check converter columns are removed
    assert f'{attr1_uuid}_converter' not in result.columns
    assert f'{attr2_uuid}_converter' not in result.columns
