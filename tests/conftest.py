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

import sqlite3
from datetime import datetime

import pandas as pd
import pytest
from _pytest.monkeypatch import MonkeyPatch

from pp_terminal.domain.schemas import AccountType, TransactionType
from pp_terminal.utils import config as config_module


TAX_RATE = (0.25 + 0.055*0.25) * 100
EXEMPT_RATE_CONFIG = {
    "attributes": {
        "securities": {
            "exempt-rate": "2baac2d0-459b-4b41-a0ef-d7dad0866892"
        }
    }
}


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, '_loaded_config', {})


@pytest.fixture(autouse=True)
def patch_db(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr('ppxml2db.dbhelper.db', sqlite3.connect(':memory:'))


@pytest.fixture(name='sample_accounts')
def provide_sample_accounts() -> pd.DataFrame:
    securities_accounts = pd.DataFrame([
        ['Testdepot', AccountType.SECURITIES.value, 'EUR'],
        ['Testkonto', AccountType.DEPOSIT.value, 'EUR'],
    ], columns=['name', 'type', 'currency'], index=['1', '2'])
    securities_accounts.index.name = 'accountId'

    return securities_accounts


@pytest.fixture(name='sample_transactions')
def provide_sample_transactions() -> pd.DataFrame:
    return (pd.DataFrame([
            [datetime(2018, 8, 15), TransactionType.BUY.value, 1000.0, 5.0, '1234567890', '1', AccountType.SECURITIES.value, 'EUR', 0.0, 0.0],
            [datetime(2018, 1, 30), TransactionType.TRANSFER_IN.value, 100000.0, 0, None, '2', AccountType.DEPOSIT.value, 'EUR', 0.0, 0.0],
    ], columns=['date', 'type', 'amount', 'shares', 'securityId', 'accountId', 'accountType', 'currency', 'taxes', 'fees'])
            .set_index(['date', 'accountId', 'securityId']))
