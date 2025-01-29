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

import logging
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from pandera.typing import DataFrame

from .portfolio_service import PortfolioService
from .schemas import TransactionSchema, AccountSchema, SecuritySchema, SecurityPriceSchema
from .ppxml2db_wrapper import PortfolioPerformanceDbWrapper

log = logging.getLogger(__name__)

_SCALE = 100000000
_CENTS_PER_EURO = 100
_ATTRIBUTE_EXEMPT_LABEL = 'Teilfreistellung'


class PortfolioPerformanceService(PortfolioService):
    _db: PortfolioPerformanceDbWrapper

    def __init__(self, file: Path):
        self._db = PortfolioPerformanceDbWrapper()
        self._db.import_file(file)

        super().__init__(
            accounts=self._parse_accounts(),
            transactions=self._parse_transactions(),
            securities=self._parse_securities(),
            prices=self._parse_prices()
        )

        self.base_currency = str(self._get_property('baseCurrency'))

        self._db.close()

    def _parse_securities(self) -> DataFrame[SecuritySchema]:
        securities = (pd.read_sql_query("""
select s.*, MAX(CASE WHEN at.name like ? THEN sa.value END) AS exempt_rate
from security as s
left join security_attr as sa on sa."security" = s.uuid
left join attribute_type as at on sa.attr_uuid = at.id
group by s.uuid
        """, self._db.connection, index_col=['uuid'], params=['%{_ATTRIBUTE_EXEMPT_LABEL}%'])
                      .rename(columns={'uuid': 'SecurityId', 'name': 'Name', 'wkn': 'Wkn', 'isRetired': 'is_retired'}))

        return cast(DataFrame[SecuritySchema], securities)

    def _parse_prices(self) -> DataFrame[SecurityPriceSchema]:
        prices = (pd.read_sql_query('select datetime(tstamp) as Date, * from price', self._db.connection, index_col=['Date', 'security'], parse_dates={"Date": "%Y-%m-%d %H:%M:%S"}, dtype={'value': np.float64})
                          .rename(columns={'security': 'SecurityId', 'tstamp': 'Date', 'value': 'Price'}))[['Price']]
        prices['Price'] = prices['Price'] / _SCALE
        prices.index.set_names(['Date', 'SecurityId'], inplace=True)

        return cast(DataFrame[SecurityPriceSchema], prices)

    def _parse_transactions(self) -> DataFrame[TransactionSchema]:
        transactions = (pd.read_sql_query("""
select datetime(date) as Date, currency, amount-fees as amount_wo_fees, fees, uuid, account, type, security, shares, acctype from xact
        """, self._db.connection, index_col=['Date', 'account', 'security'], parse_dates={"Date": "%Y-%m-%d %H:%M:%S"}, dtype={'amount_wo_fees': np.float64, 'shares': np.float64})
                          .rename(columns={'uuid': 'TransactionId', 'account': 'AccountId', 'type': 'Type', 'security': 'SecurityId', 'shares': 'Shares', 'acctype': 'account_type', 'amount_wo_fees': 'amount'}))
        transactions['amount'] = transactions['amount'] / _CENTS_PER_EURO
        transactions['Shares'] = transactions['Shares'] / _SCALE
        transactions['Type'] = pd.Categorical(transactions['Type'])
        transactions.index.set_names(['Date', 'AccountId', 'SecurityId'], inplace=True)

        return cast(DataFrame[TransactionSchema], transactions)

    def _parse_accounts(self) -> DataFrame[AccountSchema]:
        accounts = (pd.read_sql_query('select * from account', self._db.connection, index_col='uuid')
                          .rename(columns={'uuid': 'AccountId', 'type': 'Type', 'name': 'Name', 'referenceAccount': 'ReferenceAccountId', 'isRetired': 'is_retired'}))

        return cast(DataFrame[AccountSchema], accounts)

    def _get_property(self, name: str) -> str | None:
        cursor = self._db.connection.cursor()
        cursor.execute('select value from property where name = ?', (name, ))

        result = cursor.fetchone()
        if result is None:
            return None

        return str(result[0])
