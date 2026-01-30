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

import pandas as pd
import typer
from pandera.typing import DataFrame
from typing_extensions import Annotated

from pp_terminal.data.cost_basis import match_sales_to_lots
from pp_terminal.data.filters import filter_by_type
from pp_terminal.data.tax import load_prepaid_tax_data_from_csv, calculate_prepaid_tax_per_lot, FifoLot
from pp_terminal.exceptions import InputError
from pp_terminal.utils.helper import format_money, footer
from pp_terminal.utils.options import tax_rate_callback, tax_csv_callback
from pp_terminal.output.strategy import OutputStrategy, Console
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.portfolio import Portfolio, get_securities_account_by_id, get_security_by_id
from pp_terminal.domain.schemas import TransactionType, Percent, Money, TaxPaidSchema, Account, Security, FifoLotSchema, TransactionSchema
from pp_terminal.output.table_decorator import TableOptions

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def _calculate_fifo_lots(  # pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
        snapshot: PortfolioSnapshot,
        account_id: str,
        security_id: str,
        shares_to_sell: float,
        sale_price: Money,
        tax_rate: Percent,
        tax_csv_data: DataFrame[TaxPaidSchema] | None = None
) -> DataFrame[FifoLotSchema]:
    """
    Calculate FIFO lots for shares being sold, including prepaid tax calculations.
    """
    transactions = snapshot.securities_account_transactions

    # Step 1: Get purchase transactions for this account/security from snapshot
    purchase_txns : DataFrame[TransactionSchema] = transactions[
        (transactions.index.get_level_values('accountId') == account_id) &
        (transactions.index.get_level_values('securityId') == security_id)
    ].pipe(filter_by_type, transaction_types=[TransactionType.BUY, TransactionType.DELIVERY_INBOUND])

    if purchase_txns.empty:
        raise InputError(f"No purchase transactions found for security {security_id} in account {account_id}")

    # Step 2: Convert purchase transactions to lots using shared logic pattern
    purchase_txns_sorted = purchase_txns.sort_index(level='date')
    account_lots: list[FifoLot] = []

    for (date, _, _), row in purchase_txns_sorted.iterrows():
        shares = float(row['shares'])
        if shares <= 0:
            continue

        # BUY transactions have negative amounts (cash outflow), use absolute value
        purchase_price = abs(float(row['amount']) / shares)

        account_lots.append({
            'purchase_date': date,
            'account_id': account_id,
            'shares': shares,
            'purchase_price': purchase_price,
            'cost_basis': shares * purchase_price,
            'capital_gain': 0.0
        })

    # Step 3: Get historical sells for this account/security
    historical_sells = transactions[
        (transactions.index.get_level_values('accountId') == account_id) &
        (transactions.index.get_level_values('securityId') == security_id)
    ].pipe(filter_by_type, transaction_types=[TransactionType.SELL, TransactionType.DELIVERY_OUTBOUND])

    # Step 4: Match historical sells to lots using shared FIFO logic
    account_lots_df = pd.DataFrame(account_lots)
    if not account_lots_df.empty:
        account_lots_df['security_id'] = security_id
    remaining_lots_df = match_sales_to_lots(account_lots_df, historical_sells)

    # Step 5: Match the hypothetical sell against remaining lots
    if remaining_lots_df.empty:
        raise InputError(f"Insufficient shares available. Requested: {shares_to_sell}, Available: 0")

    # Calculate cumulative shares to determine lot consumption
    cumsum = remaining_lots_df['shares'].cumsum()
    prev_cumsum = cumsum.shift(1, fill_value=0.0)

    # Shares to take from each lot: min(lot_shares, remaining_needed)
    shares_taken = (shares_to_sell - prev_cumsum).clip(lower=0, upper=remaining_lots_df['shares'])

    # Filter to contributing lots only
    contributing_mask = shares_taken > 0
    if not contributing_mask.any():
        raise InputError(f"Insufficient shares available. Requested: {shares_to_sell}, Available: 0")

    df = remaining_lots_df[contributing_mask][['purchase_date', 'account_id', 'purchase_price']].copy()
    df['shares'] = shares_taken[contributing_mask].values

    # Validate sufficient shares
    total_allocated = df['shares'].sum()
    if total_allocated < shares_to_sell - 0.0001:  # Allow small floating point errors
        raise InputError(
            f"Insufficient shares available. Requested: {shares_to_sell}, "
            f"Available: {total_allocated}"
        )

    df['cost_basis'] = df['shares'] * df['purchase_price']
    df['capital_gain'] = df['shares'] * (sale_price - df['purchase_price'])
    df['security_id'] = security_id
    df['salePrice'] = sale_price
    df['grossProceeds'] = df['shares'] * sale_price

    prepaid_tax_series = calculate_prepaid_tax_per_lot(FifoLotSchema.validate(df), snapshot.date, tax_csv_data)
    df['prepaidTax'] = prepaid_tax_series.values

    df['taxableGain'] = df.apply(lambda row: max(0.0, row['capital_gain'] - row['prepaidTax']), axis=1)
    df['totalTax'] = df['taxableGain'] * (tax_rate / 100.0)
    df['netProceeds'] = df['grossProceeds'] - df['totalTax']

    return FifoLotSchema.validate(df)


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

    _tax_csv_data = load_prepaid_tax_data_from_csv(tax_csv, tax_rate) if tax_csv else None

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

    fifo_lots = _calculate_fifo_lots(snapshot, account_id, security_id, shares, sale_price, tax_rate, _tax_csv_data)
    fifo_lots['currency'] = security.currency

    console.print(output.text(f"\n[bold]Security:[/bold] {security.name} ({security.wkn})"))
    console.print(output.text(f"[bold]Account:[/bold] {account.name}"))
    console.print(output.text(f"[bold]Shares:[/bold] {shares}"))
    console.print(output.text(f"[bold]Sale Date:[/bold] {date.strftime('%Y-%m-%d')}"))
    console.print(output.text(f"[bold]Sale Price (per share):[/bold] {format_money(sale_price, security.currency)}"))

    console.print(*output.result_table(
        fifo_lots,
        TableOptions(title="FIFO Lots Breakdown", show_index=False, show_total=True)
    ))

    console.print(output.warning(f'This simulation assumes all values are in security currency ({security.currency}) excl. Sparerpauschbetrag.'))
    console.print(output.text(footer()), style="dim")
