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
# pylint: disable=protected-access

import pandas as pd
import numpy as np
from _pytest.logging import LogCaptureFixture

from pp_terminal.pp_portfolio_builder import PpPortfolioBuilder


def test_normalize_exempt_rate_percent_plain_converter() -> None:
    """Test PercentPlainConverter normalization (10 -> 0.1)."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF A', 'ETF B', 'ETF C'],
        'Wkn': ['A1', 'B1', 'C1'],
        'exempt_rate': ['30', '15', '100'],  # 30%, 15%, 100%
        'exempt_rate_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
        ]
    })

    result = builder._normalize_exempt_rate(securities)

    assert result.loc[0, 'exempt_rate'] == 0.30
    assert result.loc[1, 'exempt_rate'] == 0.15
    assert result.loc[2, 'exempt_rate'] == 1.0
    assert 'exempt_rate_converter' not in result.columns


def test_normalize_exempt_rate_percent_converter() -> None:
    """Test PercentConverter normalization (0.3 -> 0.3)."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF A', 'ETF B', 'ETF C'],
        'Wkn': ['A1', 'B1', 'C1'],
        'exempt_rate': ['0.3', '0.15', '1.0'],  # 30%, 15%, 100%
        'exempt_rate_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentConverter',
        ]
    })

    result = builder._normalize_exempt_rate(securities)

    assert result.loc[0, 'exempt_rate'] == 0.30
    assert result.loc[1, 'exempt_rate'] == 0.15
    assert result.loc[2, 'exempt_rate'] == 1.0
    assert 'exempt_rate_converter' not in result.columns


def test_exempt_rate_validation_out_of_range(caplog: LogCaptureFixture) -> None:
    """Test validation rejects values outside [1%, 100%] range."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF Too Low', 'ETF Too High', 'ETF Valid'],
        'Wkn': ['LOW1', 'HIGH1', 'OK1'],
        'exempt_rate': ['-0.5', '150', '30'],
        'exempt_rate_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
        ]
    })

    result = builder._normalize_exempt_rate(securities)

    # Too low (0.5%) should be rejected
    assert pd.isna(result.loc[0, 'exempt_rate'])
    assert 'Invalid exempt_rate for security \'ETF Too Low\' (WKN: LOW1): -0.0050 (-0.50%) is outside valid range [0%, 100%]' in caplog.text

    # Too high (150%) should be rejected
    assert pd.isna(result.loc[1, 'exempt_rate'])
    assert 'Invalid exempt_rate for security \'ETF Too High\' (WKN: HIGH1): 1.5000 (150.00%) is outside valid range [0%, 100%]' in caplog.text

    # Valid (30%) should be accepted
    assert result.loc[2, 'exempt_rate'] == 0.30


def test_exempt_rate_edge_cases(caplog: LogCaptureFixture) -> None:
    """Test edge cases: exactly 1% and exactly 100%."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF Min', 'ETF Max'],
        'Wkn': ['MIN1', 'MAX1'],
        'exempt_rate': ['1', '100'],  # 1%, 100%
        'exempt_rate_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
        ]
    })

    result = builder._normalize_exempt_rate(securities)

    # Both edge values should be accepted
    assert result.loc[0, 'exempt_rate'] == 0.01
    assert result.loc[1, 'exempt_rate'] == 1.0

    # No warnings should be logged
    assert 'Invalid exempt_rate' not in caplog.text


def test_exempt_rate_unknown_converter(caplog: LogCaptureFixture) -> None:
    """Test handling of unknown converter type."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF Unknown'],
        'Wkn': ['UNK1'],
        'exempt_rate': ['30'],
        'exempt_rate_converter': ['some.unknown.Converter'],
    })

    result = builder._normalize_exempt_rate(securities)

    # Unknown converter should be rejected
    assert pd.isna(result.loc[0, 'exempt_rate'])
    assert 'Unknown exempt_rate converter type \'some.unknown.Converter\' for security \'ETF Unknown\' (WKN: UNK1)' in caplog.text


def test_exempt_rate_invalid_format(caplog: LogCaptureFixture) -> None:
    """Test handling of unparseable exempt_rate values."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF Invalid'],
        'Wkn': ['INV1'],
        'exempt_rate': ['invalid'],
        'exempt_rate_converter': ['name.abuchen.portfolio.model.AttributeType$PercentPlainConverter'],
    })

    result = builder._normalize_exempt_rate(securities)

    # Invalid format should be rejected
    assert pd.isna(result.loc[0, 'exempt_rate'])
    assert 'Failed to parse exempt_rate \'invalid\' for security \'ETF Invalid\' (WKN: INV1)' in caplog.text


def test_exempt_rate_missing_values(caplog: LogCaptureFixture) -> None:
    """Test handling of missing exempt_rate or converter values."""
    builder = PpPortfolioBuilder()

    securities = pd.DataFrame({
        'Name': ['ETF No Rate', 'ETF No Converter', 'ETF Both Missing'],
        'Wkn': ['NR1', 'NC1', 'BM1'],
        'exempt_rate': [np.nan, '30', np.nan],
        'exempt_rate_converter': [
            'name.abuchen.portfolio.model.AttributeType$PercentPlainConverter',
            np.nan,
            np.nan,
        ]
    })

    result = builder._normalize_exempt_rate(securities)

    # All should be NaN
    assert pd.isna(result.loc[0, 'exempt_rate'])  # No rate -> stays NaN
    assert pd.isna(result.loc[1, 'exempt_rate'])  # No converter -> set to NaN with warning
    assert pd.isna(result.loc[2, 'exempt_rate'])  # Both missing -> stays NaN
    assert 'exempt_rate_converter' not in result.columns

    # Warning should be logged for missing converter
    assert 'Missing converter type for exempt_rate of security \'ETF No Converter\' (WKN: NC1)' in caplog.text
