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

import pytest
from _pytest.fixtures import TopRequest

from pp_terminal.utils.config import validated_toml_loader


def test_should_load_config_from_env_var_when_no_cli_config(monkeypatch: pytest.MonkeyPatch, request: TopRequest) -> None:
    monkeypatch.setenv('PP_TERMINAL_CONFIG', str(request.path.parent.parent / 'fixtures' / 'minimal.toml'))

    result = validated_toml_loader('')

    assert result.get('precision') == 4
    assert result.get('tax', {}).get('rate') == pytest.approx(27.375)

def test_should_ignore_env_var_when_cli_config_provided(monkeypatch: pytest.MonkeyPatch, request: TopRequest) -> None:
    monkeypatch.setenv('PP_TERMINAL_CONFIG', str(request.path.parent.parent / 'fixtures' / 'kommer.toml'))

    result = validated_toml_loader(str(request.path.parent.parent / 'fixtures' / 'minimal.toml'))

    assert 'commands' not in result

def test_should_return_empty_config_when_no_cli_config_and_no_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('PP_TERMINAL_CONFIG', raising=False)

    result = validated_toml_loader('')

    assert result == {}
