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

from .exceptions import InputError


def normalize_columns(
    requested_columns: list[str],
    available_columns: list[str],
    attribute_map: dict[str, str] | None = None
) -> list[str]:
    """
    Normalize and validate column names (case-insensitive matching).

    Args:
        requested_columns: List of column names requested by user
        available_columns: List of actual column names in the dataframe
        attribute_map: Optional mapping of friendly attribute names to UUID column names

    Returns:
        List of normalized column names matching the dataframe columns
    """
    normalized = []
    available_lower = {col.lower(): col for col in available_columns}

    # Create reverse mapping for attribute names (friendly name -> UUID)
    attr_name_to_uuid = {}
    if attribute_map:
        for friendly_name, uuid in attribute_map.items():
            attr_name_to_uuid[friendly_name.lower()] = uuid

    for col in requested_columns:
        col_lower = col.strip().lower()

        # Try direct column match first
        if col_lower in available_lower:
            normalized.append(available_lower[col_lower])
        # Try attribute name mapping
        elif col_lower in attr_name_to_uuid:
            uuid_col = attr_name_to_uuid[col_lower]
            if uuid_col in available_columns:
                normalized.append(uuid_col)
            else:
                raise InputError(f"Attribute '{col}' (UUID: {uuid_col}) not found in data")
        else:
            # Build helpful error message including attribute names
            # Filter out internal columns (starting with _) and UUID columns
            uuid_values = set(attribute_map.values()) if attribute_map else set()
            available_names = sorted([
                col for col in available_columns
                if not col.startswith('_') and col not in uuid_values
            ])
            if attribute_map:
                available_names.extend(f"{name} (attribute)" for name in sorted(attribute_map.keys()))
            raise InputError(f"Column '{col}' not found. Available columns: {', '.join(available_names)}")

    return normalized


def rename_uuid_columns(df: pd.DataFrame, attribute_map: dict[str, str] | None) -> pd.DataFrame:
    """
    Rename UUID columns to friendly names.

    Args:
        df: DataFrame with UUID column names
        attribute_map: Mapping of friendly names to UUID column names

    Returns:
        DataFrame with renamed columns
    """
    if attribute_map:
        uuid_to_name = {uuid: name for name, uuid in attribute_map.items()}
        rename_map = {col: uuid_to_name[col] for col in df.columns if col in uuid_to_name}
        if rename_map:
            return df.rename(columns=rename_map)
    return df
