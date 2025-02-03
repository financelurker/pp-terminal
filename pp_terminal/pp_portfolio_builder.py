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
import os
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from pandera.typing import DataFrame

from .helper import enum_list_to_values
from .portfolio import Portfolio
from .schemas import TransactionSchema, AccountSchema, SecuritySchema, SecurityPriceSchema, TransactionType
from .ppxml2db_wrapper import Ppxml2dbWrapper, DB_NAME_IN_MEMORY

log = logging.getLogger(__name__)

_SCALE = 100000000
_CENTS_PER_EURO = 100
_ATTRIBUTE_EXEMPT_LABEL = 'Teilfreistellung'
_NEGATIVE_DEPOSIT_ACCOUNT_TRANSACTION_TYPES = [
    TransactionType.TRANSFER_OUT,
    TransactionType.REMOVAL,
    TransactionType.INTEREST_CHARGE,
    TransactionType.FEES,
    TransactionType.TAXES,
    TransactionType.BUY,
]


class PpPortfolioBuilder:  # pylint: disable=too-few-public-methods
    _db: Ppxml2dbWrapper

    def __init__(self, cache_file: str | None = None):
        if cache_file is not None and os.path.exists(cache_file):
            log.debug('erasing old database "%s"', cache_file)
            os.remove(cache_file)

        self._db = Ppxml2dbWrapper(dbname=cache_file if cache_file is not None else DB_NAME_IN_MEMORY)

    def construct(self, file: Path) -> Portfolio:
        self._db.open(file)

        portfolio = Portfolio(
            accounts = self._parse_accounts(),
            transactions = self._parse_transactions(),
            securities = self._parse_securities(),
            prices = self._parse_prices()
        )

        portfolio.base_currency = str(self._get_property('baseCurrency'))

        self._db.close()

        return portfolio

    def _parse_securities(self) -> DataFrame[SecuritySchema]:
        securities = (pd.read_sql_query("""
select s.*, MAX(CASE WHEN at.name like ? THEN sa.value END) AS exempt_rate
from security as s
left join security_attr as sa on sa."security" = s.uuid
left join attribute_type as at on sa.attr_uuid = at.id
group by s.uuid
        """, self._db.connection, index_col=['uuid'], params=[f"%{_ATTRIBUTE_EXEMPT_LABEL}%"])
                      .rename(columns={'uuid': 'SecurityId', 'name': 'Name', 'wkn': 'Wkn', 'isRetired': 'is_retired'}))

        return cast(DataFrame[SecuritySchema], securities)

    def _parse_prices(self) -> DataFrame[SecurityPriceSchema]:
        prices = (pd.read_sql_query('select datetime(tstamp) as date, * from price', self._db.connection, index_col=['date', 'security'], parse_dates={"date": "%Y-%m-%d %H:%M:%S"}, dtype={'value': np.float64})
                          .rename(columns={'security': 'SecurityId', 'tstamp': 'date', 'value': 'Price'}))[['Price']]
        prices['Price'] = prices['Price'] / _SCALE
        prices.index.set_names(['date', 'SecurityId'], inplace=True)

        return cast(DataFrame[SecurityPriceSchema], prices)

    def _parse_transactions(self) -> DataFrame[TransactionSchema]:
        transactions = (pd.read_sql_query("""
select datetime(x.date) as date, ifnull(xu.forex_currency, x.currency) as currency, ifnull(xu.forex_amount, x.amount)-x.fees as amount_wo_fees, x.fees, x.taxes, x.uuid, x.account, x.type, x.security, x.shares, x.acctype
from xact as x
left join xact_unit as xu on xu.xact = x.uuid and xu.type = 'GROSS_VALUE'
        """, self._db.connection, index_col=['date', 'account', 'security'], parse_dates={"date": "%Y-%m-%d %H:%M:%S"}, dtype={'amount_wo_fees': np.float64, 'shares': np.float64})
                          .rename(columns={'uuid': 'TransactionId', 'account': 'account_id', 'type': 'Type', 'security': 'SecurityId', 'shares': 'Shares', 'acctype': 'account_type', 'amount_wo_fees': 'amount'}))
        transactions['Shares'] = transactions['Shares'] / _SCALE
        transactions['Type'] = pd.Categorical(transactions['Type'])
        transactions['amount'] = transactions.apply(
            lambda row: -1 if row['Type'] in enum_list_to_values(_NEGATIVE_DEPOSIT_ACCOUNT_TRANSACTION_TYPES) else 1,
            axis=1
        ) * transactions['amount'] / _CENTS_PER_EURO
        transactions['taxes'] = transactions['taxes'] / _CENTS_PER_EURO
        transactions.index.set_names(['date', 'account_id', 'SecurityId'], inplace=True)

        return cast(DataFrame[TransactionSchema], transactions)

    def _parse_accounts(self) -> DataFrame[AccountSchema]:
        accounts = (pd.read_sql_query('select * from account', self._db.connection, index_col='uuid')
                          .rename(columns={'uuid': 'account_id', 'type': 'Type', 'name': 'Name', 'referenceAccount': 'Referenceaccount_id', 'isRetired': 'is_retired'}))

        return cast(DataFrame[AccountSchema], accounts)

    def _get_property(self, name: str) -> str | None:
        cursor = self._db.connection.cursor()
        cursor.execute('select value from property where name = ?', (name, ))

        result = cursor.fetchone()
        if result is None:
            return None

        return str(result[0])
