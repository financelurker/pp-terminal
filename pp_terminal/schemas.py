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

from enum import Enum
from typing import Optional, TypeAlias

import pandera as pa
from pandera.typing import Index, Series


Money: TypeAlias = float
Percent: TypeAlias = float


class TransactionType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    DELIVERY_INBOUND = "DELIVERY_INBOUND"
    DELIVERY_OUTBOUND = "DELIVERY_OUTBOUND"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    DEPOSIT = "DEPOSIT"
    REMOVAL = "REMOVAL"
    INTEREST = "INTEREST"
    INTEREST_CHARGE = "INTEREST_CHARGE"
    FEES_REFUND = "FEES_REFUND"
    FEES = "FEES"
    DIVIDENDS = "DIVIDENDS"
    TAXES = "TAXES"
    TAX_REFUND = "TAX_REFUND"


class AccountType(Enum):
    SECURITIES = "portfolio"
    DEPOSIT = "account"


# @todo make all lowercase

class TransactionSchema(pa.DataFrameModel):
    date: Index[pa.DateTime]
    account_id: Index[str]
    SecurityId: Optional[str]
    Type: Series[str]  # @todo use pandera preprocessing?
    amount: Series[Money]
    Shares: Series[float]
    account_type: Series[str]


class AccountSchema(pa.DataFrameModel):
    account_id: Index[str]
    Name: Series[str]
    Type: Series[str]  # @todo use pandera preprocessing?
    Referenceaccount_id: Optional[Series[str]] = pa.Field(nullable=True)
    is_retired: Optional[Series[bool]] = pa.Field(coerce=True)


class SecuritySchema(pa.DataFrameModel):
    SecurityId: Index[str]
    Name: Series[str]
    Wkn: Series[str] = pa.Field(nullable=True)
    currency: Series[str] = pa.Field(nullable=True)


class SecurityPriceSchema(pa.DataFrameModel):
    date: Index[pa.DateTime]
    SecurityId: Index[str]
    Price: Series[Money]
