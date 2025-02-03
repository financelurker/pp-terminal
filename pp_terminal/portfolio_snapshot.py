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
from typing import cast

import pandas as pd
import pandera as pa
from pandera.typing import DataFrame

from .df_filter import filter_earlier_than, filter_by_type
from .helper import enum_list_to_values
from .portfolio import Portfolio
from .schemas import TransactionType, TransactionSchema


_NEGATIVE_SECURITIES_ACCOUNT_TRANSACTION_TYPES = [
    TransactionType.SELL,
    TransactionType.DELIVERY_OUTBOUND,
    TransactionType.TRANSFER_OUT,
]

class PortfolioSnapshot:
    _per_date: datetime
    _portfolio: Portfolio

    def __init__(self, portfolio: Portfolio, per_date: datetime = datetime.now()):
        self._portfolio = portfolio
        self._per_date = per_date

    @property
    def date(self) -> datetime:
        return self._per_date

    @property
    def portfolio(self) -> Portfolio:
        return self._portfolio

    @property
    def prices(self) -> pd.DataFrame:
        return self._portfolio.prices.pipe(filter_earlier_than, target_date=self._per_date).sort_index(level='date', ascending=False)

    @property
    def latest_prices(self) -> pd.Series:
        prices = self.prices.groupby('SecurityId').head(1).reset_index('date')['Price']
        prices.name = 'Prices'

        return prices

    @property
    @pa.check_types()
    def transactions(self) -> DataFrame[TransactionSchema] | None:  # @todo rename
        transactions = self._portfolio.securities_account_transactions
        if transactions is None:
            return None

        return cast(DataFrame[TransactionSchema], transactions.pipe(filter_earlier_than, target_date=self._per_date))

    @property
    @pa.check_types()
    def deposit_account_transactions(self) -> DataFrame[TransactionSchema] | None:
        transactions = self.portfolio.deposit_account_transactions
        if transactions is None:
            return None

        return cast(DataFrame[TransactionSchema], transactions.pipe(filter_earlier_than, target_date=self._per_date))

    @property
    @pa.check_types()
    def shares(self) -> pd.Series | None:
        transactions = self.transactions
        if transactions is None:
            return None

        transactions['Shares'] = transactions.apply(
            lambda row: -1 if row['Type'] in enum_list_to_values(_NEGATIVE_SECURITIES_ACCOUNT_TRANSACTION_TYPES) else 1,
            axis=1
        ) * transactions['Shares']

        shares = transactions.pipe(filter_by_type, transaction_types=[
            TransactionType.BUY,
            TransactionType.SELL,
            TransactionType.TRANSFER_IN,
            TransactionType.TRANSFER_OUT,
            TransactionType.DELIVERY_INBOUND,
            TransactionType.DELIVERY_OUTBOUND
        ]).groupby(['account_id', 'SecurityId', 'currency'])['Shares'].sum()
        shares.name = 'Shares'

        return shares

    @property
    def values(self) -> pd.Series:
        shares = self.shares
        if shares is None or shares.empty or self.latest_prices.empty:
            return pd.Series([], name='Balance', index=pd.MultiIndex.from_tuples([], names=['account_id', 'SecurityId', 'currency']), dtype='float64')

        values = self.latest_prices * shares
        values.name = 'Balance'

        return values.groupby(['account_id', 'SecurityId', 'currency']).sum()

    @property
    def balances(self) -> pd.Series | None:
        transactions = self.deposit_account_transactions
        if transactions is None:
            return None

        balances = transactions.groupby(['account_id', 'currency'])['amount'].sum()
        balances.name = 'Balance'

        return balances
