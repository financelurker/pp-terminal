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

import locale
from datetime import datetime
from typing import List, Any

import pandas as pd
from rich.console import Console
import typer

from .schemas import TransactionType

locale.setlocale(locale.LC_ALL, '')


def format_money(value: float) -> str:
    return locale.format_string("EUR %.2f", value, grouping=True, monetary=True) if not pd.isna(value) and isinstance(value, float) else ''


def drop_empty_df_values(df: pd.DataFrame | pd.Series) -> pd.DataFrame:
    if df.empty:
        return df

    df = df[~(df.isna() | df == 0)]

    df.dropna(how='all', axis=0, inplace=True)
    if isinstance(df, pd.DataFrame):
        df.dropna(how='all', axis=1, inplace=True)

    return df


def print_hint(console: Console, message: str) -> None:
    console.print(':bulb: [bold]Hint:[/bold] ' + message)
    console.print()


def handle_nothing_found(console: Console) -> Exception:
    console.print('Nothing here..:sleeping: ')

    return typer.Exit()


def filter_df_by_date(df: pd.DataFrame, end_date: datetime) -> pd.DataFrame:
    return df[df.index.get_level_values('Date') <= end_date]


def filter_df_by_type(df: pd.DataFrame, transaction_types: TransactionType| list[TransactionType]) -> pd.DataFrame:
    if not isinstance(transaction_types, list):
        transaction_types = [transaction_types]

    # we store only the name of the enum to save some space, so we have to convert it here
    cleaned_transaction_types = []
    for transaction_type in transaction_types:
        cleaned_transaction_types.append(transaction_type.name)

    return df[df['Type'].isin(cleaned_transaction_types)]


def enum_types_to_name(enum_list: List[Any]) -> List[Any]:
    # prepare for enum storage in dataframe
    for element in enum_list:
        element['Type'] = element['Type'].name

    return enum_list


def enum_list_to_values(enum_list: List[Any]) -> List[Any]:
    return [item.value for item in enum_list]
