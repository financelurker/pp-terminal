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

import sqlite3
import os
import logging
from pathlib import Path

from ppxml2db.ppxml2db import PortfolioPerformanceXML2DB
from ppxml2db import dbhelper

from .exceptions import InputError

log = logging.getLogger(__name__)
logging.getLogger('ppxml2db.dbhelper').setLevel(logging.INFO)  # reducing some "noise"


DB_NAME_IN_MEMORY = ':memory:'


class Ppxml2dbWrapper:
    _connection: sqlite3.Connection
    _setup_scripts_path: str
    _cursor: sqlite3.Cursor

    def __init__(self, dbname: str = DB_NAME_IN_MEMORY) -> None:
        self._setup_scripts_path = os.path.dirname(dbhelper.__file__) + '/'

        try:
            dbhelper.init(dbname)  # type: ignore
            if dbhelper.db is None:
                raise RuntimeError('could not establish database connection')

            self._connection = dbhelper.db  # @todo db connection is global state!
            self._cursor = self._connection.cursor()
            self._install()
        except Exception as e:
            raise RuntimeError('error during database initialization for ' + dbname) from e

    def open(self, file: Path) -> None:
        try:
            conv = PortfolioPerformanceXML2DB(file.open(mode='rb'))  # type: ignore
            conv.iterparse()  # type: ignore

            self._connection.commit()

            self._validate()
        except FileNotFoundError as e:
            raise e
        except Exception as e:
            raise InputError('unable to import the Portfolio Performance xml file "' + file.name + '" (is it saved as "XML with ids"?)') from e

    def close(self) -> None:
        self._connection.close()  # database is deleted

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def _install(self) -> None:
        self._create_tables(os.listdir(self._setup_scripts_path))

    def _create_tables(self, setup_scripts: list[str]) -> None:
        for filename in setup_scripts:
            if filename.endswith('.sql'):
                self._run_script(filename)

    def _run_script(self, filename: str) -> None:
        with open(self._setup_scripts_path + filename, 'r', encoding='utf-8') as sql_file:
            sql_script = sql_file.read()

        self._cursor.executescript(sql_script)
        log.debug('sql script "%s" successfully executed', filename)

    def _validate(self) -> None:
        self._cursor.execute("select value as client_version from property where name = 'version'")
        row = self._cursor.fetchone()
        if row is None:
            raise RuntimeError('missing client version in xml file')
