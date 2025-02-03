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
from typing import cast

from pandera.errors import SchemaError
from pandera.typing import DataFrame

from .schemas import AccountType, TransactionSchema, AccountSchema, SecuritySchema, SecurityPriceSchema

log = logging.getLogger(__name__)


class Portfolio:
    _accounts: DataFrame[AccountSchema] | None = None
    _securities: DataFrame[SecuritySchema] | None = None
    _transactions: DataFrame[TransactionSchema] | None = None
    _prices: DataFrame[SecurityPriceSchema] | None = None
    base_currency: str = ''

    def __init__(
            self,
            accounts: DataFrame[AccountSchema],
            transactions: DataFrame[TransactionSchema],
            securities: DataFrame[SecuritySchema],
            prices: DataFrame[SecurityPriceSchema]
    ):
        try:
            self._accounts = AccountSchema.validate(accounts)  # type: ignore
        except SchemaError as e:
            log.error('accounts schema invalid: %s', e)

        try:
            self._securities = SecuritySchema.validate(securities)  # type: ignore
        except SchemaError as e:
            log.error('securities schema invalid: %s', e)

        try:
            self._transactions = TransactionSchema.validate(transactions)  # type: ignore
        except SchemaError as e:
            log.error('transactions schema invalid: %s', e)

        try:
            self._prices = SecurityPriceSchema.validate(prices)  # type: ignore
        except SchemaError as e:
            log.error('security prices schema invalid: %s', e)

    @property
    def securities_accounts(self) -> DataFrame[AccountSchema] | None:
        if self._accounts is None:
            return None

        return cast(DataFrame[AccountSchema], self._accounts[self._accounts['Type'] == AccountType.SECURITIES.value])

    @property
    def deposit_accounts(self) -> DataFrame[AccountSchema] | None:
        if self._accounts is None:
            return None

        return cast(DataFrame[AccountSchema], self._accounts[self._accounts['Type'] == AccountType.DEPOSIT.value])

    @property
    def securities_account_transactions(self) -> DataFrame[TransactionSchema] | None:
        if self._transactions is None:
            return None

        return cast(DataFrame[TransactionSchema], self._transactions[self._transactions['account_type'] == AccountType.SECURITIES.value].sort_values(by=['date']))

    @property
    def deposit_account_transactions(self) -> DataFrame[TransactionSchema] | None:
        if self._transactions is None:
            return None

        return cast(DataFrame[TransactionSchema], self._transactions[self._transactions['account_type'] == AccountType.DEPOSIT.value].sort_values(by=['date']))

    @property
    def securities(self) -> DataFrame[SecuritySchema] | None:
        return self._securities

    @property
    def prices(self) -> DataFrame[SecurityPriceSchema]:
        return cast(DataFrame[SecurityPriceSchema], self._prices)
