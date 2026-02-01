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

import pandas as pd
from pandera.typing import DataFrame

from pp_terminal.data.filters import filter_by_type, filter_by_security
from pp_terminal.data.tax import calculate_prepaid_tax_per_lot
from pp_terminal.domain.schemas import TransactionType, Money, TransactionSchema, TaxPaidSchema, TaxLotSchema, Percent
from pp_terminal.exceptions import InputError

log = logging.getLogger(__name__)


def _filter_purchase_transactions(transactions: DataFrame[TransactionSchema]) -> DataFrame[TransactionSchema]:
    valid_purchases = transactions.pipe(filter_by_type, transaction_types=[TransactionType.BUY, TransactionType.DELIVERY_INBOUND]).sort_index(level='date')
    valid_purchases = valid_purchases[valid_purchases['shares'] > 0].copy()

    return TransactionSchema.validate(valid_purchases)


def _get_remaining_lots_after_fifo_matching(
    transactions: DataFrame[TransactionSchema]
) -> DataFrame[TaxLotSchema]:
    """
    Match all sell transactions to purchase lots using FIFO and return remaining lots.

    Returns:
        DataFrame of remaining lots after sales are matched.
        Each lot's 'shares' field represents remaining quantity.
        Exhausted lots (shares = 0) are removed.

    Implementation Note:
        FIFO matching is inherently sequential (each sale consumes lots in order,
        affecting state for the next sale). While the function accepts/returns DataFrames
        for schema validation and interface consistency, internally we use list of dicts
        for ~10x faster mutation during the matching algorithm. DataFrame .loc[] access
        has significant overhead that doesn't add value for sequential state updates.
    """
    lots = _filter_purchase_transactions(transactions)
    lots['purchasePrice'] = lots['amount'].abs() / lots['shares']  # save original purchase price
    lots = lots.rename(columns={'amount': 'cost'})
    if lots.empty:
        return TaxLotSchema.validate(lots)

    sell_transactions = transactions.pipe(filter_by_type, transaction_types=[TransactionType.SELL, TransactionType.DELIVERY_OUTBOUND])
    if sell_transactions.empty:
        return TaxLotSchema.validate(lots)

    # Convert to list of dicts for fast mutation during FIFO matching
    remaining_lots = lots.reset_index().to_dict('records')
    sales_sorted = sell_transactions.sort_index(level='date')

    for (_date, account_id, _security_id), row in sales_sorted.iterrows():
        shares_to_match = float(row['shares'])

        # Match against lots in FIFO order (only from same account)
        for lot in remaining_lots:
            if shares_to_match <= 0:
                break

            if lot['accountId'] != account_id:
                continue

            # Consume shares from this lot
            lot_shares = lot['shares']
            shares_from_lot = min(shares_to_match, lot_shares)
            new_shares = lot_shares - shares_from_lot
            shares_to_match -= shares_from_lot

            lot['shares'] = new_shares

        if shares_to_match > 0.0001:  # Allow small floating point errors
            log.warning('Sale of %.8f shares for security %s could not be fully matched to purchase lots', shares_to_match, _security_id)

    # Filter out exhausted lots and convert back to DataFrame
    remaining_lots = [lot for lot in remaining_lots if lot['shares'] > 0.0001]
    if not remaining_lots:
        return TaxLotSchema.empty()

    return TaxLotSchema.validate(pd.DataFrame(remaining_lots).set_index(['date', 'accountId', 'securityId']))


def _reduce_shares(remaining_lots_df: DataFrame[TaxLotSchema], shares_to_sell: float) -> DataFrame[TaxLotSchema]:
    # Calculate cumulative shares to determine lot consumption
    cumsum = remaining_lots_df['shares'].cumsum()
    prev_cumsum = cumsum.shift(1, fill_value=0.0)

    # Shares to take from each lot: min(lot_shares, remaining_needed)
    shares_taken = (shares_to_sell - prev_cumsum).clip(lower=0, upper=remaining_lots_df['shares'])

    # Filter to contributing lots only
    contributing_mask = shares_taken > 0
    if not contributing_mask.any():
        raise InputError(f"Insufficient shares available. Requested: {shares_to_sell}, Available: 0")

    df = remaining_lots_df[contributing_mask].copy()
    df['shares'] = shares_taken[contributing_mask].values

    # Validate sufficient shares
    total_allocated = df['shares'].sum()
    if total_allocated < shares_to_sell - 0.0001:  # Allow small floating point errors
        raise InputError(f"Insufficient shares available. Requested: {shares_to_sell}, Available: {total_allocated}")

    return TaxLotSchema.validate(df)


def _sync_amount_with_shares(df: DataFrame[TaxLotSchema]) -> DataFrame[TaxLotSchema]:
    """Adjust cost field to reflect remaining shares after FIFO matching (cost = purchasePrice * remaining shares)."""
    df = df.copy()
    df['cost'] = df['purchasePrice'] * df['shares']
    return TaxLotSchema.validate(df)


def _calculate_sell_metrics(df: DataFrame[TaxLotSchema]) -> DataFrame[TaxLotSchema]:
    """Calculate capital gains, gross proceeds, and taxable gain for sale simulation."""
    df = _sync_amount_with_shares(df)
    df['capitalGain'] = df['shares'] * (df['salePrice'] - df['purchasePrice'])
    df['grossProceeds'] = df['shares'] * df['salePrice']
    df['taxableGain'] = df.apply(lambda row: max(0.0, row['capitalGain'] - row['prepaidTax']), axis=1)

    return TaxLotSchema.validate(df)


def calculate_fifo_sell(  # pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
        transactions: DataFrame[TransactionSchema],
        sale_date: datetime,
        sale_price: Money,
        tax_rate: Percent,
        shares_to_sell: float | None = None,
        tax_csv_data: DataFrame[TaxPaidSchema] | None = None
) -> DataFrame[TaxLotSchema]:
    """Calculate FIFO lots for shares being sold, including prepaid tax calculations."""
    df = transactions.copy()

    df = _get_remaining_lots_after_fifo_matching(df)
    if df.empty:
        return TaxLotSchema.empty()

    if shares_to_sell is not None:
        df = _reduce_shares(df, shares_to_sell)

    df = TaxLotSchema.validate(df)
    df['salePrice'] = sale_price

    df['prepaidTax'] = calculate_prepaid_tax_per_lot(df, sale_date, tax_csv_data).values

    df = _calculate_sell_metrics(df)
    df['totalTax'] = df['taxableGain'] * (tax_rate / 100.0)
    df['netProceeds'] = df['grossProceeds'] - df['totalTax']

    return TaxLotSchema.validate(df)


def calculate_total_cost(transactions: DataFrame[TransactionSchema], security_id: str) -> Money:
    """Calculate the cost basis of currently held shares for a security, i.e. what did I originally pay for the shares I currently hold?"""
    df = transactions.pipe(filter_by_security, security_id=security_id)
    df = _get_remaining_lots_after_fifo_matching(df)
    if df.empty:
        return Money(0.0)

    df = _sync_amount_with_shares(df)

    return Money(df['cost'].abs().sum())
