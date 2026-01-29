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
from typing import TypedDict, cast

import pandas as pd
import typer
from pandera.typing import DataFrame
from typing_extensions import Annotated

from pp_terminal.data.cost_basis import match_sales_to_lots
from pp_terminal.data.filters import filter_by_type
from pp_terminal.data.tax import load_prepaid_tax_data_from_csv, calculate_prepaid_tax_for_lots, FifoLot
from pp_terminal.exceptions import InputError
from pp_terminal.utils.helper import format_money, footer
from pp_terminal.utils.options import tax_rate_callback, tax_csv_callback
from pp_terminal.output.strategy import OutputStrategy, Console
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.portfolio import Portfolio, get_securities_account_by_id, get_security_by_id
from pp_terminal.domain.schemas import TransactionType, Percent, Money, TaxPaidSchema, Account, Security
from pp_terminal.output.table_decorator import TableOptions

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


class TaxBreakdown(TypedDict):
    taxable_gain: Money
    total_tax: Money


def _calculate_fifo_lots(  # pylint: disable=too-many-locals
        snapshot: PortfolioSnapshot,
        account_id: str,
        security_id: str,
        shares_to_sell: float,
        sale_price: Money
) -> list[FifoLot]:
    """
    Calculate FIFO lots for shares being sold.
    Returns list of lots with purchase info and capital gains.
    """
    transactions = snapshot.securities_account_transactions

    # Step 1: Get purchase transactions for this account/security from snapshot
    purchase_txns = transactions[
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

    # Step 3: Get historical sales for this account/security
    historical_sales = transactions[
        (transactions.index.get_level_values('accountId') == account_id) &
        (transactions.index.get_level_values('securityId') == security_id)
    ].pipe(filter_by_type, transaction_types=[TransactionType.SELL, TransactionType.DELIVERY_OUTBOUND])

    # Step 4: Match historical sales to lots using shared FIFO logic
    remaining_lots = match_sales_to_lots(account_lots, historical_sales)

    # Step 5: Match the hypothetical sale against remaining lots
    lots_to_return: list[FifoLot] = []
    shares_remaining = shares_to_sell

    for lot in remaining_lots:
        if shares_remaining <= 0:
            break

        shares_from_lot = min(shares_remaining, lot['shares'])
        capital_gain = shares_from_lot * (sale_price - lot['purchase_price'])

        lots_to_return.append({
            'purchase_date': lot['purchase_date'],
            'account_id': lot['account_id'],
            'shares': shares_from_lot,
            'purchase_price': lot['purchase_price'],
            'cost_basis': shares_from_lot * lot['purchase_price'],
            'capital_gain': capital_gain
        })

        shares_remaining -= shares_from_lot

    if shares_remaining > 0.0001:  # Allow small floating point errors
        raise InputError(f"Insufficient shares available. Requested: {shares_to_sell}, Available: {shares_to_sell - shares_remaining}")

    return lots_to_return


def _calculate_prepaid_taxes_for_lots(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        account_id: str,  # pylint: disable=unused-argument
        security_id: str,
        fifo_lots: list[FifoLot],
        sale_date: datetime,
        tax_csv_data: DataFrame[TaxPaidSchema] | None
) -> Money:
    return calculate_prepaid_tax_for_lots(fifo_lots, security_id, sale_date, tax_csv_data)


def _calculate_taxes(
        capital_gain: Money,
        vorabpauschale_credit: Money,
        tax_rate: Percent
) -> TaxBreakdown:
    """
    Calculate taxes on capital gains after Vorabpauschale credit.
    """
    taxable_gain = max(0, capital_gain - vorabpauschale_credit)
    total_tax = taxable_gain * (tax_rate / 100)

    return {
        'taxable_gain': taxable_gain,
        'total_tax': total_tax
    }


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

    tax_csv_data = load_prepaid_tax_data_from_csv(tax_csv, tax_rate) if tax_csv else None

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

    fifo_lots = _calculate_fifo_lots(snapshot, account_id, security_id, shares, sale_price)
    lots_df = pd.DataFrame(fifo_lots)
    lots_df['salePrice'] = sale_price
    lots_df['grossProceeds'] = lots_df['shares'] * sale_price
    lots_df['currency'] = security.currency

    total_cost_basis = sum(lot['cost_basis'] for lot in fifo_lots)
    total_capital_gain = sum(lot['capital_gain'] for lot in fifo_lots)
    gross_proceeds = shares * sale_price

    taxes_paid = calculate_prepaid_tax_for_lots(fifo_lots, security_id, date, tax_csv_data)

    taxes = _calculate_taxes(total_capital_gain, taxes_paid, tax_rate)
    net_proceeds = gross_proceeds - taxes['total_tax']

    effective_tax_rate = (taxes['total_tax'] / gross_proceeds * 100) if gross_proceeds > 0 else 0

    summary_df = pd.DataFrame({
        'Description': [
            'Gross Proceeds',
            'Total Cost Basis',
            'Taxes Already Paid',
            f'Total Tax ({effective_tax_rate:.3f}%)',
            'Net Proceeds'
        ],
        'amount': [
            gross_proceeds,
            -total_cost_basis,
            -taxes_paid,
            taxes['total_tax'],
            net_proceeds
        ],
        'currency': [security.currency] * 5
    })

    lots_df_2 = pd.DataFrame({
        'Purchase Date': [lot['purchase_date'].strftime('%Y-%m-%d') for lot in fifo_lots],
        'Shares': [lot['shares'] for lot in fifo_lots],
        'Purchase Price': [lot['purchase_price'] for lot in fifo_lots],
        'Sale Price': [sale_price] * len(fifo_lots),
        'Cost Basis': [lot['cost_basis'] for lot in fifo_lots],
        'Capital Gain': [lot['capital_gain'] for lot in fifo_lots],
        'Gross Proceeds': [lot['shares'] * sale_price for lot in fifo_lots],
        'Taxes Already Paid': calculate_prepaid_tax_for_lots(fifo_lots, security_id, date, tax_csv_data),
        'Remaining Taxes': [max(0.00, lot['capital_gain'] - calculate_prepaid_tax_for_lots(fifo_lots, security_id, date, tax_csv_data)) * tax_rate/100 for lot in fifo_lots],
        'Net Proceeds': [lot['shares'] * sale_price - max(0.00, lot['capital_gain'] - calculate_prepaid_tax_for_lots(fifo_lots, security_id, date, tax_csv_data)) * tax_rate/100 for lot in fifo_lots],
        'currency': [security.currency] * len(fifo_lots)
    })

    console.print(output.text(f"\n[bold]Security:[/bold] {security.name} ({security.wkn})"))
    console.print(output.text(f"[bold]Account:[/bold] {account.name}"))
    console.print(output.text(f"[bold]Shares:[/bold] {shares}"))
    console.print(output.text(f"[bold]Sale Date:[/bold] {date.strftime('%Y-%m-%d')}"))
    console.print(output.text(f"[bold]Sale Price (per share):[/bold] {format_money(sale_price, security.currency)}"))

    console.print(*output.result_table(
        summary_df,
        TableOptions(title="Sale Summary", show_index=False, show_total=True, footer_lines=2)
    ))

    console.print(*output.result_table(
        lots_df,
        TableOptions(title="FIFO Lots Breakdown", show_index=False, show_total=True)
    ))

    console.print(output.warning(f'This simulation assumes all values are in security currency ({security.currency}) excl. Sparerpauschbetrag.'))
    console.print(output.text(footer()), style="dim")
