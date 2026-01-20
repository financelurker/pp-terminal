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
from typing import Dict

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


def convert_attribute_types(df: pd.DataFrame, attributes: Dict[str, str]) -> pd.DataFrame:  # pylint: disable=too-many-branches
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
        converter_col = f"{attr_uuid}_converter"

        if value_col not in df.columns:
            continue

        for idx, row in df.iterrows():
            if pd.notna(row.get(value_col)):
                if pd.isna(row.get(converter_col)):
                    log.warning(
                        "Missing converter type for attribute '%s' (%s) of entity at index %s. Ignoring value.",
                        attr_name, attr_uuid, idx
                    )
                    df.at[idx, value_col] = np.nan
                    continue

                try:
                    value = row[value_col]
                    converter = str(row[converter_col])

                    if 'DateConverter' in converter:
                        df.at[idx, value_col] = pd.to_datetime(value)
                    elif 'PercentPlainConverter' in converter:
                        df.at[idx, value_col] = float(value) / 100
                    elif 'PercentConverter' in converter:
                        df.at[idx, value_col] = float(value)
                    elif 'LongConverter' in converter or 'AmountConverter' in converter:
                        df.at[idx, value_col] = float(value)
                    elif 'StringConverter' in converter:
                        df.at[idx, value_col] = str(value)
                    else:
                        log.warning(
                            "Unknown converter type '%s' for attribute '%s' (%s). Keeping raw value.",
                            converter, attr_name, attr_uuid
                        )

                except (ValueError, TypeError) as e:
                    log.warning(
                        "Failed to parse attribute '%s' (%s) value '%s': %s. Ignoring value.",
                        attr_name, attr_uuid, row[value_col], str(e)
                    )
                    df.at[idx, value_col] = np.nan

        if converter_col in df.columns:
            df = df.drop(columns=[converter_col])

    return df
