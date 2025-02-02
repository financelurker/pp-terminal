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

from pathlib import Path

import pytest
from _pytest.fixtures import TopRequest

from pp_terminal.exceptions import InputError
from pp_terminal.pp_portfolio_builder import PpPortfolioBuilder


def test_import_non_existent_file() -> None:
    with pytest.raises(FileNotFoundError):
        PpPortfolioBuilder().construct(Path('non-existing.xml'))


@pytest.mark.parametrize("xml_file", ['kommer.xml', 'invalid.xml', 'other.xml'])
def test_import_invalid_xml(request: TopRequest, xml_file: str) -> None:
    with pytest.raises(InputError):
        PpPortfolioBuilder().construct(request.path.parent / 'fixtures' / xml_file)


def test_import_pp_empty_xml(request: TopRequest) -> None:
    PpPortfolioBuilder().construct(request.path.parent / 'fixtures' / 'empty.ids.xml')
