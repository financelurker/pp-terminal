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

from pathlib import Path
from typing import Any
from unittest.mock import patch

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


def test_xml_file_opened_readonly(request: TopRequest) -> None:
    """Verify that Portfolio Performance XML files are opened in read-only mode."""
    xml_file_path = request.path.parent / 'fixtures' / 'empty.ids.xml'

    # Track the mode parameter passed to file.open()
    original_open = Path.open
    open_call_args: dict[str, Any] = {}

    def tracked_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        open_call_args['mode'] = kwargs.get('mode', 'r')
        open_call_args['path'] = self
        return original_open(self, *args, **kwargs)

    with patch.object(Path, 'open', tracked_open):
        PpPortfolioBuilder().construct(xml_file_path)

    assert 'mode' in open_call_args, "Path.open() was not called"
    assert open_call_args['mode'] == 'rb', \
        f"Expected file to be opened with mode='rb', but got mode='{open_call_args['mode']}'"
    assert open_call_args['path'] == xml_file_path, \
        f"Expected {xml_file_path} to be opened, but got {open_call_args['path']}'"
