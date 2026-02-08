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
from os import getcwd

import pytest

from pp_terminal.utils import config as config_module
from pp_terminal.utils.config import validated_toml_loader


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, '_loaded_config', {})


class TestValidatedTomlLoaderEnvVar:

    def test_should_load_config_from_env_var_when_no_cli_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PP_TERMINAL_CONFIG', getcwd()+'/../tests/fixtures/minimal.toml')

        result = validated_toml_loader('')

        assert result.get('precision') == 4
        assert result.get('tax', {}).get('rate') == 27.375

    def test_should_ignore_env_var_when_cli_config_provided(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv('PP_TERMINAL_CONFIG', getcwd()+'/../tests/fixtures/kommer.toml')

        result = validated_toml_loader(getcwd()+'/../tests/fixtures/minimal.toml')

        assert 'commands' not in result

    def test_should_return_empty_config_when_no_cli_config_and_no_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv('PP_TERMINAL_CONFIG', raising=False)

        result = validated_toml_loader('')

        assert result == {}
