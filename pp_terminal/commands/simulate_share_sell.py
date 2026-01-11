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
from typing import TypedDict, Any

import pandas as pd
import typer
from typing_extensions import Annotated

from ..df_filter import filter_by_type
from ..exceptions import InputError
from ..helper import format_money, footer
from ..options import tax_rate_callback, tax_csv_callback
from ..output import OutputStrategy, Console
from ..portfolio_snapshot import PortfolioSnapshot
from ..portfolio import Portfolio
from ..schemas import TransactionType, Percent, Money
from ..table_decorator import TableOptions

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


def _load_vorabpauschale_csv(csv_path: Path) -> pd.DataFrame:
    """
    Load Vorabpauschale tax data from CSV.
    Expected format: date;account_id;security_id;tax_per_share
    Returns DataFrame indexed by (year, account_id, security_id) with tax_per_share values.
    """
    try:
        df = pd.read_csv(csv_path, sep=';', parse_dates=['date'])
    except FileNotFoundError as e:
        raise InputError(f"Vorabpauschale CSV file not found: {csv_path}") from e
    except Exception as e:
        raise InputError(f"Failed to read Vorabpauschale CSV: {e}") from e

    required_columns = {'date', 'account_id', 'security_id', 'tax_per_share'}
    if not required_columns.issubset(df.columns):
        raise InputError(f"CSV missing required columns. Expected: {required_columns}, Got: {set(df.columns)}")

    # Extract year from date and create multi-index
    df['year'] = df['date'].dt.year
    df = df.set_index(['year', 'account_id', 'security_id'])

    return df[['tax_per_share']]


class FifoLot(TypedDict):
    purchase_date: datetime
    shares: float
    purchase_price: Money
    cost_basis: Money
    capital_gain: Money


class TaxBreakdown(TypedDict):
    taxable_gain: Money
    total_tax: Money


def _calculate_fifo_lots(
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
    transactions = snapshot.transactions
    if transactions is None:
        raise InputError("No transactions found in portfolio")

    # Filter to BUY and DELIVERY_INBOUND for this account/security
    purchase_txns = transactions[
        (transactions.index.get_level_values('account_id') == account_id) &
        (transactions.index.get_level_values('SecurityId') == security_id)
    ].pipe(filter_by_type, transaction_types=[TransactionType.BUY, TransactionType.DELIVERY_INBOUND])

    if purchase_txns.empty:
        raise InputError(f"No purchase transactions found for security {security_id} in account {account_id}")

    # Sort by date (FIFO)
    purchase_txns = purchase_txns.sort_index(level='date')

    lots: list[FifoLot] = []
    shares_remaining = shares_to_sell

    for (date, _, _), row in purchase_txns.iterrows():
        if shares_remaining <= 0:
            break

        shares_from_lot = min(shares_remaining, row['Shares'])
        # BUY transactions have negative amounts (cash outflow), use absolute value for cost basis
        purchase_price = abs(row['amount'] / row['Shares']) if row['Shares'] > 0 else 0
        cost_basis = shares_from_lot * purchase_price
        capital_gain = shares_from_lot * (sale_price - purchase_price)

        lots.append({
            'purchase_date': date,
            'shares': shares_from_lot,
            'purchase_price': purchase_price,
            'cost_basis': cost_basis,
            'capital_gain': capital_gain
        })

        shares_remaining -= shares_from_lot

    if shares_remaining > 0.0001:  # Allow small floating point errors
        raise InputError(f"Insufficient shares available. Requested: {shares_to_sell}, Available: {shares_to_sell - shares_remaining}")

    return lots


def _calculate_vorabpauschale_for_lot(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        lot: FifoLot,
        sale_date: datetime,
        account_id: str,
        security_id: str,
        vorab_csv_data: pd.DataFrame | None
) -> Money:
    """
    Calculate Vorabpauschale credit for a single FIFO lot.
    Uses per-share tax data from CSV, prorated by months held in purchase year.
    """
    if vorab_csv_data is None or vorab_csv_data.empty:
        return 0.0

    purchase_date = lot['purchase_date']
    shares_from_lot = lot['shares']

    # Determine years to include: from purchase year to sale year - 1
    first_year = purchase_date.year
    last_year = sale_date.year - 1

    if last_year < first_year:
        # Sold in same year as purchase - no Vorabpauschale
        return 0.0

    credit = 0.0

    # Calculate credit for each year
    for year in range(first_year, last_year + 1):
        # Look up tax_per_share for this year/account/security
        try:
            tax_per_share = vorab_csv_data.loc[(year, account_id, security_id), 'tax_per_share']
        except KeyError:
            # No data for this year/account/security - use 0.0 silently
            continue

        # For purchase year, prorate by months held
        if year == first_year:
            # Months held = 13 - purchase_month (e.g., June = month 6 -> 13-6 = 7 months)
            months_held = 13 - purchase_date.month
            month_factor = months_held / 12.0
        else:
            # Full year
            month_factor = 1.0

        credit += shares_from_lot * tax_per_share * month_factor

    return credit


def _calculate_vorabpauschale_credit_for_lots(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        account_id: str,
        security_id: str,
        fifo_lots: list[FifoLot],
        sale_date: datetime,
        vorab_csv_data: pd.DataFrame | None
) -> Money:
    """
    Calculate total Vorabpauschale credit for all lots being sold.
    """
    if not fifo_lots:
        return 0.0

    return sum(
        _calculate_vorabpauschale_for_lot(lot, sale_date, account_id, security_id, vorab_csv_data)
        for lot in fifo_lots
    )


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


@app.command(name="share-sell")
def simulate_share_sell(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-statements,too-many-branches
        ctx: typer.Context,
        wkn: Annotated[str, typer.Option(help="Security WKN (Wertpapierkennnummer)", prompt="Security WKN", prompt_required=True)],
        account_id: Annotated[str, typer.Option(help="Securities account ID", prompt="Account ID", prompt_required=True)],
        date: Annotated[datetime | None, typer.Option(formats=["%Y-%m-%d"], help="Sale date (defaults to today)", prompt="Sale date (YYYY-MM-DD)", prompt_required=False)] = None,
        tax_rate: Annotated[Percent, typer.Option(help="Your personal tax rate", min=0, max=100, callback=tax_rate_callback)] = None,  # type: ignore
        shares: Annotated[float | None, typer.Option(help="Number of shares to sell (defaults to all available shares)", min=0.0001)] = None,
        price: Annotated[Money | None, typer.Option(help="Sale price per share (defaults to latest market price)")] = None,
        tax_csv: Annotated[Path | None, typer.Option(help="CSV file with Vorabpauschale tax per share data", callback=tax_csv_callback)] = None
) -> None:
    """
    Simulate selling shares: calculate fees, taxes (Abgeltungssteuer + Soli), and net proceeds.
    Uses FIFO cost basis and accounts for Vorabpauschale already paid.
    """
    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy

    # Set default date if not provided
    if date is None:
        date = get_today()

    # Load Vorabpauschale CSV if provided
    vorab_csv_data = None
    if tax_csv is not None:
        log.debug('Loading Vorabpauschale tax data from "%s"', tax_csv)
        vorab_csv_data = _load_vorabpauschale_csv(tax_csv)

    # Look up security by WKN
    if portfolio.securities is None:
        raise InputError("No securities found in portfolio")

    security_match = portfolio.securities[portfolio.securities['Wkn'] == wkn]
    if security_match.empty:
        raise InputError(f"Security with WKN '{wkn}' not found in portfolio")

    security_id = security_match.index[0]
    security_info = security_match.iloc[0]
    security_name = security_info['Name']
    security_wkn = security_info['Wkn']

    # Validate account exists and is a securities account
    if portfolio.securities_accounts is None or account_id not in portfolio.securities_accounts.index:
        raise InputError(f"Securities account '{account_id}' not found in portfolio")

    account_info = portfolio.securities_accounts.loc[account_id]
    account_name = account_info['Name']

    # Create snapshot at sale date
    snapshot = PortfolioSnapshot(portfolio, date)

    # Determine sale price
    currency = security_info['currency']
    if price is None:
        latest_prices = snapshot.latest_prices
        if security_id not in latest_prices.index:
            raise InputError(f"No price data available for security '{security_id}'. Please provide --price")
        sale_price = latest_prices.loc[security_id]
    else:
        if price <= 0:
            raise InputError("Sale price must be greater than 0")
        sale_price = price

    # Verify sufficient shares available
    shares_available = snapshot.shares
    if shares_available is None:
        raise InputError("No share holdings found in portfolio")

    # Check for this specific account/security combination
    holding_key = None
    for key in shares_available.index:
        if key[0] == account_id and key[1] == security_id:
            holding_key = key
            break

    if holding_key is None:
        raise InputError(f"No shares of '{security_name}' found in account '{account_name}' on {date.strftime('%Y-%m-%d')}")

    available_shares = shares_available[holding_key]

    # If shares not specified, sell all available shares
    if shares is None:
        shares = available_shares
    elif available_shares < shares - 0.0001:  # Allow small floating point errors
        raise InputError(f"Insufficient shares. Available: {available_shares:.8f}, Requested: {shares:.8f}")

    fifo_lots = _calculate_fifo_lots(snapshot, account_id, security_id, shares, sale_price)

    total_cost_basis = sum(lot['cost_basis'] for lot in fifo_lots)
    total_capital_gain = sum(lot['capital_gain'] for lot in fifo_lots)
    gross_proceeds = shares * sale_price

    vorabpauschale_credit = _calculate_vorabpauschale_credit_for_lots(
        account_id, security_id, fifo_lots, date, vorab_csv_data
    )

    taxes = _calculate_taxes(total_capital_gain, vorabpauschale_credit, tax_rate)
    net_proceeds = gross_proceeds - taxes['total_tax']

    effective_tax_rate = (taxes['total_tax'] / gross_proceeds * 100) if gross_proceeds > 0 else 0

    summary_data = {
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
            -vorabpauschale_credit,
            taxes['total_tax'],
            net_proceeds
        ],
        'currency': [currency] * 5
    }
    summary_df = pd.DataFrame(summary_data)

    # Format output - FIFO Lots (use numeric types for proper alignment and totals)
    lots_data = {
        'Purchase Date': [lot['purchase_date'].strftime('%Y-%m-%d') for lot in fifo_lots],
        'Shares': [lot['shares'] for lot in fifo_lots],
        'Purchase Price': [lot['purchase_price'] for lot in fifo_lots],
        'Cost Basis': [lot['cost_basis'] for lot in fifo_lots],
        'Capital Gain': [lot['capital_gain'] for lot in fifo_lots],
        'Vorabpauschale': [
            _calculate_vorabpauschale_for_lot(lot, date, account_id, security_id, vorab_csv_data)
            for lot in fifo_lots
        ],
        'currency': [currency] * len(fifo_lots)
    }
    lots_df = pd.DataFrame(lots_data)

    # Custom formatter for FIFO lots - exclude currency for Shares, skip Purchase Price total
    def format_lots_value(value: Any, col_name: str, row: pd.Series) -> str:
        # Skip Purchase Price total (summing prices is meaningless)
        if col_name == 'Purchase Price' and 'Name' in row and row['Name'] == 'Total':
            return ''
        # Don't format shares with currency
        if col_name == 'Shares':
            return f"{float(value):.2f}"
        # Regular currency formatting for other columns
        if col_name in ['Purchase Price', 'Cost Basis', 'Capital Gain', 'Vorabpauschale']:
            return format_money(float(value), row['currency'])
        return str(value)

    console.print(output.text(f"\n[bold]Security:[/bold] {security_name} ({security_wkn})"))
    console.print(output.text(f"[bold]Account:[/bold] {account_name}"))
    console.print(output.text(f"[bold]Shares:[/bold] {shares}"))
    console.print(output.text(f"[bold]Sale Date:[/bold] {date.strftime('%Y-%m-%d')}"))
    console.print(output.text(f"[bold]Sale Price (per share):[/bold] {format_money(sale_price, currency)}"))

    console.print(*output.result_table(
        summary_df,
        TableOptions(title="Sale Summary", show_index=False, show_total=True, footer_lines=2)
    ))

    console.print(*output.result_table(
        lots_df,
        TableOptions(title="FIFO Lots Breakdown", show_index=False, show_total=True, value_formatter=format_lots_value)
    ))

    console.print(output.warning(f'This simulation assumes all values are in security currency ({currency}) excl. Sparerpauschbetrag.'))
    console.print(output.text(footer()), style="dim")
