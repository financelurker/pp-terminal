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

from datetime import datetime
import logging
from pathlib import Path
from typing import cast
from typing_extensions import Annotated

import typer
from pp_terminal.data.filters import filter_by_account_and_security
from pp_terminal.domain.cost_basis import calculate_fifo_sell

from pp_terminal.data.tax import load_prepaid_tax_data_from_csv
from pp_terminal.exceptions import InputError
from pp_terminal.utils.helper import footer
from pp_terminal.utils.options import tax_rate_callback, tax_csv_callback
from pp_terminal.output.strategy import OutputStrategy, Console
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.portfolio import Portfolio, get_securities_account_by_id, get_security_by_id
from pp_terminal.domain.schemas import Percent, Money, Account, Security
from pp_terminal.output.table_decorator import TableOptions

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def get_today() -> datetime:
    """Return today's date at midnight."""
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _get_available_shares(security: Security, account: Account, snapshot: PortfolioSnapshot) -> float:
    shares_available = snapshot.shares
    if shares_available is None:
        raise InputError("No share holdings found in portfolio")

    # Check for this specific account/security combination
    holding_key = None
    for key in shares_available.index:
        if key[0] == account.accountId and key[1] == security.securityId:
            holding_key = key
            break

    if holding_key is None:
        raise InputError(f"No shares of '{security.name}' found in account '{account.name}' on {snapshot.date.strftime('%Y-%m-%d')}")

    return float(shares_available[holding_key])


@app.command(name="share-sell")
def simulate_share_sell(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-statements,too-many-branches
        ctx: typer.Context,
        security_id: Annotated[str, typer.Option(prompt="Security ID", prompt_required=True)],
        account_id: Annotated[str, typer.Option(help="Securities account ID", prompt="Account ID", prompt_required=True)],
        date: Annotated[datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Sale date (defaults to today)", prompt="Sale date (YYYY-MM-DD)", prompt_required=False)] = None,
        tax_rate: Annotated[Percent, typer.Option(help="Your personal tax rate", min=0, max=100, callback=tax_rate_callback)] = None,  # type: ignore
        shares: Annotated[float | None, typer.Option(help="Number of shares to sell (defaults to all available shares)", min=0.0001)] = None,
        price: Annotated[Money | None, typer.Option(help="Sale price per share (defaults to latest market price)")] = None,
        tax_csv: Annotated[Path | None, typer.Option(help="CSV file with paid tax per share data", callback=tax_csv_callback)] = None
) -> None:
    """
    Simulate selling shares: calculate fees, taxes (Abgeltungssteuer + Soli), and net proceeds.
    Uses FIFO cost basis and accounts for taxes already paid.
    """
    portfolio = cast(Portfolio, ctx.obj.portfolio)
    output = cast(OutputStrategy, ctx.obj.output)

    if date is None:
        date = get_today()

    try:
        _tax_csv_data = load_prepaid_tax_data_from_csv(tax_csv, tax_rate) if tax_csv else None
    except InputError as e:
        log.error("unable to load prepaid tax from csv, skipping: %s", e)
        _tax_csv_data = None

    security = get_security_by_id(portfolio, security_id)
    account = get_securities_account_by_id(portfolio, account_id)
    snapshot = PortfolioSnapshot(portfolio, date)

    # Determine sale price
    if price is None:
        latest_prices = snapshot.latest_prices
        if security_id not in latest_prices.index:
            raise InputError(f"No price data available for security '{security_id}'. Please provide --price")
        sale_price = latest_prices.loc[security_id]
    elif price <= 0:
        raise InputError("Sale price must be greater than 0")
    else:
        sale_price = price

    available_shares = _get_available_shares(security, account, snapshot)
    if shares is None:
        shares = available_shares
    elif available_shares < shares - 0.0001:  # Allow small floating point errors
        raise InputError(f"Insufficient shares. Available: {available_shares:.8f}, Requested: {shares:.8f}")

    transactions = snapshot.securities_account_transactions.pipe(filter_by_account_and_security, security_id=security_id, account_id=account_id)
    fifo_lots = calculate_fifo_sell(transactions, snapshot.date, sale_price, tax_rate, shares, _tax_csv_data).reset_index()

    console.print(*output.result_table(
        fifo_lots[['date', 'shares', 'currency', 'purchasePrice', 'costBasis', 'fees', 'salePrice', 'capitalGain', 'prepaidTax', 'taxableGain', 'grossProceeds', 'totalTax', 'netProceeds']],
        TableOptions(title=f"FIFO Lots on {date.strftime('%Y-%m-%d')}", caption=f"{security.name} ({security.wkn}) in {account.name}", show_index=False, show_total=True)
    ))

    console.print(output.warning(f'This simulation assumes all values are in security currency ({security.currency}) excl. Sparerpauschbetrag.'))
    console.print(output.text(footer()), style="dim")
