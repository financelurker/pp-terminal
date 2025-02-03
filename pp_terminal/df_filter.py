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

from datetime import datetime

import pandas as pd

from .schemas import TransactionType


def filter_earlier_than(df: pd.DataFrame, target_date: datetime) -> pd.DataFrame:
    return df[df.index.get_level_values('date') <= target_date]


def filter_later_than(df: pd.DataFrame, target_date: datetime) -> pd.DataFrame:
    return df[df.index.get_level_values('date') >= target_date]


def filter_by_account_id(df: pd.DataFrame, account_id: str) -> pd.DataFrame:
    return df[df.index.get_level_values('account_id') == account_id]


def filter_by_type(df: pd.DataFrame, transaction_types: TransactionType| list[TransactionType]) -> pd.DataFrame:
    if not isinstance(transaction_types, list):
        transaction_types = [transaction_types]

    # we store only the name of the enum to save some space, so we have to convert it here
    cleaned_transaction_types = []
    for transaction_type in transaction_types:
        cleaned_transaction_types.append(transaction_type.name)

    return df[df['Type'].isin(cleaned_transaction_types)]


def filter_not_retired(df: pd.DataFrame) -> pd.DataFrame:
    return df[df['is_retired'] != True]  # pylint: disable=singleton-comparison


def drop_empty_values(df: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if df.empty:
        return df

    df = df[~(df.isna() | df == 0)]

    df.dropna(how='all', axis=0, inplace=True)
    if isinstance(df, pd.DataFrame):
        df.dropna(how='all', axis=1, inplace=True)

    return df


def unstack_column_by_currency(df: pd.DataFrame, column: str, base_currency: str) -> pd.DataFrame:
    column_unstacked = df[column].unstack(level='currency')
    df_modified = df.drop(columns=column).reset_index(level='currency', drop=True)
    df_modified = df_modified[~df_modified.index.get_level_values('account_id').duplicated()]  # drop duplicates ignoring currency

    df_modified = df_modified.join(column_unstacked, how='outer')

    if base_currency in df_modified:
        df_modified.sort_values(by=base_currency, inplace=True)

    return df_modified
