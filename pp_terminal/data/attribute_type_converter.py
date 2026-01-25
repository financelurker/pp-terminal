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
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

def _percent_plain_converter(value: Any) -> float:
    """Convert percent value stored as plain number (divide by 100)."""
    return float(value) / 100


CONVERTER_DISPATCH: Dict[str, Callable[[Any], Any]] = {
    'DateConverter': pd.to_datetime,
    'PercentPlainConverter': _percent_plain_converter,
    'PercentConverter': float,
    'LongConverter': float,
    'AmountConverter': float,
    'StringConverter': str,
}


def _get_converter_function(converter: str) -> Optional[Callable[[Any], Any]]:
    """Get the conversion function for a given converter class name."""
    for key, func in CONVERTER_DISPATCH.items():
        if key in converter:
            return func
    return None


def _convert_single_value(value: Any, converter: Any, attr_name: str, attr_uuid: str, idx: Any) -> Any:
    """
    Convert a single attribute value based on its converter type.

    Args:
        value: The raw attribute value to convert
        converter: The converter class name
        attr_name: Friendly name of the attribute (for logging)
        attr_uuid: UUID of the attribute (for logging)
        idx: Row index (for logging)

    Returns:
        Converted value or np.nan if conversion fails
    """
    if pd.isna(value):
        return value

    if pd.isna(converter):
        log.warning(
            "Missing converter type for attribute '%s' (%s) of entity at index %s. Ignoring value.",
            attr_name, attr_uuid, idx
        )
        return np.nan

    converter_str = str(converter)
    convert_func = _get_converter_function(converter_str)

    if convert_func is None:
        log.warning(
            "Unknown converter type '%s' for attribute '%s' (%s). Keeping raw value.",
            converter_str, attr_name, attr_uuid
        )
        return value

    try:
        return convert_func(value)
    except (ValueError, TypeError) as e:
        log.warning(
            "Failed to parse attribute '%s' (%s) value '%s': %s. Ignoring value.",
            attr_name, attr_uuid, value, str(e)
        )
        return np.nan


def convert_attribute_types(df: pd.DataFrame, attributes: Dict[str, str]) -> pd.DataFrame:
    """
    Convert attribute values based on their converterClass types.

    Portfolio Performance stores attribute metadata including a converterClass that indicates
    how to interpret the stored string value. This function transforms those string values
    into their proper Python types (float, datetime, etc.).

    Args:
        df: DataFrame containing attribute columns (as UUIDs) and corresponding
            {uuid}_converter columns with converter class names
        attributes: Dictionary mapping friendly attribute names to their UUIDs

    Returns:
        DataFrame with converted attribute values and converter columns removed
    """
    for attr_name, attr_uuid in attributes.items():
        value_col = attr_uuid
        converter_col = get_converter_column_name(attr_uuid)

        if value_col not in df.columns:
            continue

        df[value_col] = df.apply(
            lambda row, value_column=value_col, converter_column=converter_col, attribute_name=attr_name, attribute_uuid=attr_uuid: _convert_single_value(
                row.get(value_column),
                row.get(converter_column),
                attribute_name,
                attribute_uuid,
                row.name
            ),
            axis=1
        )

        if converter_col in df.columns:
            df = df.drop(columns=[converter_col])

    return df

def get_converter_column_name(attr_uuid: str) -> str:
    return f"_{attr_uuid}_converter"
