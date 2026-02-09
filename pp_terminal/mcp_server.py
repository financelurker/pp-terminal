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
import math
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import typer
from mcp.server.fastmcp import FastMCP

from pp_terminal.commands.view_accounts import prepare_accounts_df
from pp_terminal.commands.view_securities import prepare_securities_df
from pp_terminal.domain.schemas import AccountType
from pp_terminal.data.pp_portfolio_builder import CachedPpPortfolioBuilder
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.utils.cache import checksum
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.vap import calculate_vap, get_base_rate_for_year, add_account_balances
from pp_terminal.utils.config import Config, get_tax_rate, get_exempt_rate, get_exempt_rate_attribute

log = logging.getLogger(__name__)
_SERVER_NAME = "pp-mcp"


def _is_empty(value: Any) -> bool:
    if value is None or value is pd.NaT or value == '':
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def _clean_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records = df.to_dict(orient='records')
    return [
        {k: v for k, v in record.items() if not _is_empty(v)}
        for record in records
    ]

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
        df = prepare_securities_df(portfolio, config, by_date, active, in_stock)
        return _clean_records(df)

    @mcp.tool()
    def view_accounts(
        by: str | None = None,
        account_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all accounts with balances and validation messages. Optional account_type: DEPOSIT or SECURITIES."""
        portfolio = _ensure_fresh_portfolio()
        by_date = datetime.fromisoformat(by) if by else datetime.now()
        parsed_type = AccountType(account_type) if account_type else None
        df = prepare_accounts_df(portfolio, config, by_date, parsed_type)
        return _clean_records(df.reset_index())

    @mcp.tool()
    def simulate_vap(
        year: int | None = None,
        base_rate: float | None = None,
        tax_rate: float | None = None,
        exempt_rate: float | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate German preliminary tax (Vorabpauschale/VAP) per security and account for a given year (§18 InvStG).

        Args:
            year: Tax year (defaults to last year)
            base_rate: Base interest rate / Basiszinssatz in percent (defaults to official rate for the year)
            tax_rate: Personal tax rate in percent (defaults to config or 26.375%)
            exempt_rate: Default exemption rate / Teilfreistellung in percent (defaults to config or 30%)
        """
        portfolio = _ensure_fresh_portfolio()
        effective_year = year if year is not None else datetime.now().year - 1

        base_rate_pct = base_rate if base_rate is not None else get_base_rate_for_year(effective_year)
        tax_rate_pct = tax_rate if tax_rate is not None else get_tax_rate(config)
        exempt_rate_pct = exempt_rate if exempt_rate is not None else get_exempt_rate(config)
        exempt_rate_uuid = get_exempt_rate_attribute(config)

        snapshot_begin = PortfolioSnapshot(portfolio, datetime(effective_year, 1, 2))
        snapshot_end = PortfolioSnapshot(portfolio, datetime(effective_year, 12, 31))

        result = calculate_vap(
            snapshot_begin, snapshot_end,
            base_rate_pct, tax_rate_pct, exempt_rate_pct, exempt_rate_uuid
        )

        if result.empty:
            return []

        result = add_account_balances(result, portfolio, snapshot_end)
        return _clean_records(result)

    return mcp


def start_mcp(ctx: typer.Context) -> None:
    """Start MCP server for AI client access to portfolio data."""
    file_path = cast(Path, ctx.obj.source_file)
    config = cast(Config, ctx.obj.config)

    mcp = create_mcp_server(file_path, config)
    mcp.run(transport='stdio')
