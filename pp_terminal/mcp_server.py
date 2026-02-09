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
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import typer
from mcp.server.fastmcp import FastMCP

from pp_terminal.commands.view_accounts import prepare_accounts_dataframe
from pp_terminal.commands.view_securities import prepare_securities_dataframe
from pp_terminal.domain.schemas import AccountType
from pp_terminal.data.pp_portfolio_builder import CachedPpPortfolioBuilder
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.utils.cache import checksum
from pp_terminal.utils.config import Config

log = logging.getLogger(__name__)
_SERVER_NAME = "pp-mcp"

def create_mcp_server(file_path: Path, config: Config) -> FastMCP:
    builder = CachedPpPortfolioBuilder(config=config)
    state: dict[str, Any] = {
        'portfolio': builder.construct(file_path),
        'checksum': checksum(file_path),
    }

    mcp = FastMCP(_SERVER_NAME)

    def _ensure_fresh_portfolio() -> Portfolio:
        current_checksum = checksum(file_path)
        if current_checksum != state['checksum']:
            log.info("XML file changed, rebuilding portfolio")
            state['portfolio'] = builder.construct(file_path)
            state['checksum'] = current_checksum
        return cast(Portfolio, state['portfolio'])

    @mcp.tool()
    def view_securities(
        by: str | None = None,
        active: bool = False,
        in_stock: bool = False,
    ) -> list[dict[str, Any]]:
        """List all securities with shares, cost basis, validation messages, and Vorabpauschale."""
        portfolio = _ensure_fresh_portfolio()
        by_date = datetime.fromisoformat(by) if by else datetime.now()
        df = prepare_securities_dataframe(portfolio, config, by_date, active, in_stock)
        return cast(list[dict[str, Any]], df.to_dict(orient='records'))

    @mcp.tool()
    def view_accounts(
        by: str | None = None,
        account_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all accounts with balances and validation messages. Optional account_type: DEPOSIT or SECURITIES."""
        portfolio = _ensure_fresh_portfolio()
        by_date = datetime.fromisoformat(by) if by else datetime.now()
        parsed_type = AccountType(account_type) if account_type else None
        df = prepare_accounts_dataframe(portfolio, config, by_date, parsed_type)
        return cast(list[dict[str, Any]], df.reset_index().to_dict(orient='records'))

    return mcp


def start_mcp(ctx: typer.Context) -> None:
    """Start MCP server for AI client access to portfolio data."""
    file_path = cast(Path, ctx.obj.source_file)
    config = cast(Config, ctx.obj.config)

    mcp = create_mcp_server(file_path, config)
    mcp.run(transport='stdio')
