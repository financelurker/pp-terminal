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
from pathlib import Path
from typing import Any, Dict, cast

import numpy as np
import pandas as pd
from pandera.typing import DataFrame

from .cache_utils import cleanup_old_cache_files, get_cache_path
from .helper import enum_list_to_values
from .portfolio import Portfolio
from .schemas import TransactionSchema, AccountSchema, SecuritySchema, SecurityPriceSchema, TransactionType
from .ppxml2db_wrapper import Ppxml2dbWrapper, DB_NAME_IN_MEMORY

log = logging.getLogger(__name__)

_SCALE = 100000000
_CENTS_PER_EURO = 100
_EXEMPT_RATE_MIN = 0.00
_EXEMPT_RATE_MAX = 1.0
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
    _config: Dict[str, Any]
    _use_cache: bool

    def __init__(self, config: Dict[str, Any] | None = None, use_cache: bool = True):
        self._config = config if config is not None else {}
        self._use_cache = use_cache

    def construct(self, file: Path) -> Portfolio:
        cache_path: Path | None = None
        use_cache_file = False

        if self._use_cache:
            try:
                cache_path = get_cache_path(file)

                # Check if cache file exists
                if cache_path.exists():
                    log.debug('Using cache from "%s"', cache_path)
                    use_cache_file = True
                else:
                    log.debug('Cache not found, will create at "%s"', cache_path)

            except (OSError, IOError) as e:
                # Cache I/O error - fall back to in-memory
                log.warning(
                    'Cache unavailable due to I/O error (%s), using in-memory database',
                    str(e)
                )
                cache_path = None

        # Initialize database connection
        try:
            if cache_path is not None:
                self._db = Ppxml2dbWrapper(dbname=str(cache_path))
            else:
                log.debug('Using in-memory database')
                self._db = Ppxml2dbWrapper(dbname=DB_NAME_IN_MEMORY)
        except Exception as e:  # pylint: disable=broad-exception-caught
            # DB initialization error - fall back to in-memory
            log.warning(
                'Failed to initialize cache database (%s), using in-memory database',
                str(e)
            )
            self._db = Ppxml2dbWrapper(dbname=DB_NAME_IN_MEMORY)
            cache_path = None
            use_cache_file = False

        # Parse XML if cache miss or in-memory mode
        if not use_cache_file:
            self._db.open(file)

            # Cleanup old cache files after successful parse
            if cache_path is not None:
                try:
                    cleanup_old_cache_files(file)
                    log.debug('Cleaned up old cache files')
                except Exception as e:  # pylint: disable=broad-exception-caught
                    log.warning('Failed to cleanup old cache files: %s', str(e))

        # Build portfolio from database (same for both cache hit and miss)
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
        exempt_attr_uuid = self._config.get('attributes', {}).get('exemption-rate')

        if exempt_attr_uuid:
            # Use UUID-based query, verify UUID exists
            cursor = self._db.connection.cursor()
            cursor.execute('SELECT id FROM attribute_type WHERE id = ?', (exempt_attr_uuid,))
            if cursor.fetchone() is None:
                raise RuntimeError(f"Configured exemption-rate attribute UUID '{exempt_attr_uuid}' not found in Portfolio Performance database")

        securities = (pd.read_sql_query("""
select s.*,
   MAX(CASE WHEN at.id = ? THEN sa.value END) AS exempt_rate,
   MAX(CASE WHEN at.id = ? THEN at.converterClass END) AS exempt_rate_converter
from security as s
left join security_attr as sa on sa."security" = s.uuid
left join attribute_type as at on sa.attr_uuid = at.id
group by s.uuid
        """, self._db.connection, index_col=['uuid'], params=[exempt_attr_uuid, exempt_attr_uuid])
                      .rename(columns={'uuid': 'SecurityId', 'name': 'Name', 'wkn': 'Wkn', 'isRetired': 'is_retired'}))

        # Normalize and validate exempt_rate
        if 'exempt_rate' in securities.columns and 'exempt_rate_converter' in securities.columns:
            securities = self._normalize_exempt_rate(securities)

        return cast(DataFrame[SecuritySchema], securities)

    def _normalize_exempt_rate(self, securities: pd.DataFrame) -> pd.DataFrame:
        """Normalize and validate exempt_rate values based on converter type."""
        for idx, row in securities.iterrows():
            if pd.notna(row['exempt_rate']):
                # If exempt_rate exists but converter is missing, we can't normalize
                if pd.isna(row['exempt_rate_converter']):
                    log.warning(
                        "Missing converter type for exempt_rate of security '%s' (WKN: %s). Ignoring value.",
                        row['Name'], row.get('Wkn', 'N/A')
                    )
                    securities.at[idx, 'exempt_rate'] = np.nan
                    continue

                try:
                    value = float(row['exempt_rate'])
                    converter = str(row['exempt_rate_converter'])

                    # Normalize based on converter type
                    if 'PercentPlainConverter' in converter:
                        # PercentPlainConverter: 10 means 10%, so divide by 100
                        normalized_value = value / 100
                    elif 'PercentConverter' in converter:
                        # PercentConverter: 0.1 means 10%, use as-is
                        normalized_value = value
                    else:
                        log.warning(
                            "Unknown exempt_rate converter type '%s' for security '%s' (WKN: %s). Ignoring value.",
                            converter, row['Name'], row.get('Wkn', 'N/A')
                        )
                        securities.at[idx, 'exempt_rate'] = np.nan
                        continue

                    # Validate range: 1% to 100%
                    if normalized_value < _EXEMPT_RATE_MIN or normalized_value > _EXEMPT_RATE_MAX:
                        log.warning(
                            "Invalid exempt_rate for security '%s' (WKN: %s): %.4f (%.2f%%) is outside valid range [%.0f%%, %.0f%%]. Ignoring value.",
                            row['Name'], row.get('Wkn', 'N/A'),
                            normalized_value, normalized_value * 100,
                            _EXEMPT_RATE_MIN * 100, _EXEMPT_RATE_MAX * 100
                        )
                        securities.at[idx, 'exempt_rate'] = np.nan
                    else:
                        securities.at[idx, 'exempt_rate'] = normalized_value

                except (ValueError, TypeError) as e:
                    log.warning(
                        "Failed to parse exempt_rate '%s' for security '%s' (WKN: %s): %s. Ignoring value.",
                        row['exempt_rate'], row['Name'], row.get('Wkn', 'N/A'), str(e)
                    )
                    securities.at[idx, 'exempt_rate'] = np.nan

        # Drop the converter column as it's no longer needed
        securities = securities.drop(columns=['exempt_rate_converter'])

        return securities

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
        """, self._db.connection, index_col=['date', 'account', 'security'], parse_dates={"date": "%Y-%m-%d %H:%M:%S"}, dtype={'amount_wo_fees': np.float64, 'shares': np.float64, 'taxes': np.float64})
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
