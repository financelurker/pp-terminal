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

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import typer
from mcp.server.fastmcp import FastMCP

from pp_terminal.commands.simulate_share_sell import prepare_share_sell_df
from pp_terminal.commands.view_accounts import prepare_accounts_df
from pp_terminal.commands.view_securities import prepare_securities_df
from pp_terminal.data.filters import clean_for_display
from pp_terminal.data.tax import load_prepaid_tax_data
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType
from pp_terminal.data.pp_portfolio_builder import CachedPpPortfolioBuilder
from pp_terminal.utils.cache import checksum
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.vap import calculate_vap, get_base_rate_for_year, add_account_balances
from pp_terminal.utils.config import Config, get_tax_rate, get_exempt_rate, get_exempt_rate_attribute, get_tax_files

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

    @mcp.resource("portfolio://accounts", mime_type="application/json")
    def accounts_resource() -> str:
        """All portfolio accounts (deposit and securities) with their metadata."""
        portfolio = _ensure_fresh_portfolio()
        df = (pd.concat([portfolio.deposit_accounts, portfolio.securities_accounts])
              .reset_index()
              .pipe(clean_for_display, portfolio.account_attributes))
        return json.dumps(_clean_records(df))

    @mcp.resource("portfolio://securities", mime_type="application/json")
    def securities_resource() -> str:
        """All portfolio securities with their metadata."""
        portfolio = _ensure_fresh_portfolio()
        df = (portfolio.securities.reset_index()
              .pipe(clean_for_display, portfolio.security_attributes))
        return json.dumps(_clean_records(df))

    @mcp.tool()
    def query_securities(
        date: str | None = None,
        active: bool = False,
        in_stock: bool = False,
    ) -> list[dict[str, Any]]:
        """List all securities with shares, cost basis, validation messages, and Vorabpauschale."""
        portfolio = _ensure_fresh_portfolio()
        by_date = datetime.fromisoformat(date) if date else datetime.now()
        df = prepare_securities_df(portfolio, config, by_date, active, in_stock)
        return _clean_records(df)

    @mcp.tool()
    def query_accounts(
        date: str | None = None,
        account_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all accounts with balances and validation messages. Optional account_type: DEPOSIT or SECURITIES."""
        portfolio = _ensure_fresh_portfolio()
        by_date = datetime.fromisoformat(date) if date else datetime.now()
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

    def _sell_defaults(date: str | None, tax_rate: float | None) -> tuple[datetime, float]:
        sell_date = datetime.fromisoformat(date) if date else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        effective_tax_rate = tax_rate if tax_rate is not None else get_tax_rate(config)
        return sell_date, effective_tax_rate

    @mcp.tool()
    def query_fifo_lots(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        security_id: str | None = None,
        account_id: str | None = None,
        date: str | None = None,
        tax_rate: float | None = None,
        price: float | None = None,
    ) -> list[dict[str, Any]]:
        """List all FIFO purchase lots with projected tax on hypothetical sale.

        Each row is one purchase lot (FIFO order) showing: securityName, purchase date, shares,
        currency, purchasePrice, costBasis, fees, salePrice, grossProceeds, capitalGain,
        deemedIncome (Vorabpauschale), taxableGain, totalTax, netProceeds.

        Args:
            security_id: Filter to a single security (defaults to all securities)
            account_id: Filter to a single securities account (defaults to all accounts)
            date: Valuation date as ISO string, e.g. '2025-06-15' (defaults to today)
            tax_rate: Personal tax rate in percent (defaults to config or 26.375%)
            price: Override sale price per share (only meaningful with security_id, defaults to latest price)
        """
        portfolio = _ensure_fresh_portfolio()
        sell_date, effective_tax_rate = _sell_defaults(date, tax_rate)
        tax_csv_data = load_prepaid_tax_data(get_tax_files(config), portfolio)

        result = prepare_share_sell_df(
            portfolio, config, sell_date, effective_tax_rate,
            security_id, account_id, price=price, tax_csv_data=tax_csv_data
        )
        return _clean_records(result) if not result.empty else []

    @mcp.tool()
    def simulate_sell_shares(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        security_id: str,
        shares: float,
        account_id: str | None = None,
        date: str | None = None,
        tax_rate: float | None = None,
        price: float | None = None,
    ) -> list[dict[str, Any]]:
        """Simulate selling a specific number of shares using FIFO order.

        Returns the FIFO purchase lots consumed by the sale. Each row is one lot showing:
        securityName, purchase date, shares sold from that lot, currency, purchasePrice,
        costBasis, fees, salePrice, grossProceeds, capitalGain, deemedIncome (Vorabpauschale),
        taxableGain, totalTax, netProceeds.

        Args:
            security_id: Security to sell (required)
            shares: Number of shares to sell (required)
            account_id: Securities account ID (defaults to all accounts holding this security)
            date: Sale date as ISO string, e.g. '2025-06-15' (defaults to today)
            tax_rate: Personal tax rate in percent (defaults to config or 26.375%)
            price: Sale price per share (defaults to latest known price)
        """
        portfolio = _ensure_fresh_portfolio()
        sell_date, effective_tax_rate = _sell_defaults(date, tax_rate)
        tax_csv_data = load_prepaid_tax_data(get_tax_files(config), portfolio)

        result = prepare_share_sell_df(
            portfolio, config, sell_date, effective_tax_rate,
            security_id, account_id, shares=shares, price=price, tax_csv_data=tax_csv_data
        )
        return _clean_records(result) if not result.empty else []

    @mcp.tool()
    def simulate_sell_target_net(
        target_net: float,
        security_id: str | None = None,
        account_id: str | None = None,
        date: str | None = None,
        tax_rate: float | None = None,
    ) -> list[dict[str, Any]]:
        """Find the minimum-tax combination of FIFO lots to achieve a target net proceeds amount.

        Selects lots across securities/accounts to minimize total tax while reaching the target.
        Uses latest known prices. Each row is one FIFO lot showing: securityName, purchase date,
        shares to sell, currency, purchasePrice, costBasis, fees, salePrice, grossProceeds,
        capitalGain, deemedIncome (Vorabpauschale), taxableGain, totalTax, netProceeds.

        Args:
            target_net: Target net proceeds to realize (required)
            security_id: Restrict to a single security (defaults to all securities)
            account_id: Restrict to a single securities account (defaults to all accounts)
            date: Sale date as ISO string, e.g. '2025-06-15' (defaults to today)
            tax_rate: Personal tax rate in percent (defaults to config or 26.375%)
        """
        portfolio = _ensure_fresh_portfolio()
        sell_date, effective_tax_rate = _sell_defaults(date, tax_rate)
        tax_csv_data = load_prepaid_tax_data(get_tax_files(config), portfolio)

        result = prepare_share_sell_df(
            portfolio, config, sell_date, effective_tax_rate,
            security_id, account_id, target_net=target_net, tax_csv_data=tax_csv_data
        )
        return _clean_records(result) if not result.empty else []

    return mcp


def start_mcp(ctx: typer.Context) -> None:
    """Start MCP server for AI client access to portfolio data."""
    file_path = cast(Path, ctx.obj.source_file)
    config = cast(Config, ctx.obj.config)

    mcp = create_mcp_server(file_path, config)
    mcp.run(transport='stdio')
