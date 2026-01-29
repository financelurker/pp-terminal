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

from pp_terminal.data.filters import filter_by_type
from pp_terminal.data.tax import calculate_prepaid_tax_for_lots
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import TransactionType, Money, TransactionSchema, TaxPaidSchema, FifoLotSchema

log = logging.getLogger(__name__)


def calculate_purchase_lots(
    portfolio: Portfolio,
    security_id: str,
    sort_by_date: bool = True
) -> DataFrame[FifoLotSchema]:
    """
    Get all purchase lots for a security across all accounts.
    """
    transactions = portfolio.securities_account_transactions
    purchase_txns : DataFrame[TransactionSchema] = transactions[
        transactions.index.get_level_values('securityId') == security_id
    ].pipe(filter_by_type, transaction_types=[TransactionType.BUY, TransactionType.DELIVERY_INBOUND])

    if purchase_txns.empty:
        log.debug('No purchase transactions found for security %s', security_id)
        return FifoLotSchema.empty()

    # Reset index to get date, accountId, securityId as columns
    lots = purchase_txns.reset_index()

    # Filter out zero/negative shares
    zero_shares_mask = lots['shares'] <= 0
    if zero_shares_mask.any():
        log.warning('Skipping %d transaction(s) with zero/negative shares', zero_shares_mask.sum())
        lots = lots[~zero_shares_mask]

    if lots.empty:
        return FifoLotSchema.empty()

    # Calculate purchase_price: BUY transactions have negative amounts (cash outflow)
    lots['purchase_price'] = lots['amount'].abs() / lots['shares']
    lots['cost_basis'] = lots['shares'] * lots['purchase_price']
    lots['capital_gain'] = 0.0

    lots = lots.rename(columns={'date': 'purchase_date', 'accountId': 'account_id', 'securityId': 'security_id'})
    lots = lots[['purchase_date', 'account_id', 'security_id', 'shares', 'purchase_price', 'cost_basis', 'capital_gain']]

    # Sort by date if requested (FIFO order)
    if sort_by_date:
        lots = lots.sort_values('purchase_date')

    return FifoLotSchema.validate(lots)


def match_sales_to_lots(
    lots: DataFrame[FifoLotSchema],
    sell_transactions: DataFrame[TransactionSchema]
) -> DataFrame[FifoLotSchema]:
    """
    Apply FIFO matching of sales to purchase lots.

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
    if sell_transactions.empty:
        return lots

    # Convert to list of dicts for fast mutation during FIFO matching
    remaining_lots = lots.to_dict('records')
    sales_sorted = sell_transactions.sort_index(level='date')

    for (_date, account_id, _security_id), row in sales_sorted.iterrows():
        shares_to_match = float(row['shares'])

        # Match against lots in FIFO order (only from same account)
        for lot in remaining_lots:
            if shares_to_match <= 0:
                break

            if lot['account_id'] != account_id:
                continue

            # Consume shares from this lot
            lot_shares = lot['shares']
            shares_from_lot = min(shares_to_match, lot_shares)
            new_shares = lot_shares - shares_from_lot
            shares_to_match -= shares_from_lot

            # Update shares and cost_basis
            lot['shares'] = new_shares
            if new_shares > 0:
                remaining_fraction = new_shares / lot_shares
                lot['cost_basis'] *= remaining_fraction
            else:
                lot['cost_basis'] = 0.0

        if shares_to_match > 0.0001:  # Allow small floating point errors
            log.warning('Sale of %.8f shares for security %s could not be fully matched to purchase lots', shares_to_match, _security_id)

    # Filter out exhausted lots and convert back to DataFrame
    remaining_lots = [lot for lot in remaining_lots if lot['shares'] > 0.0001]

    if not remaining_lots:
        return FifoLotSchema.empty()

    return FifoLotSchema.validate(pd.DataFrame(remaining_lots))


def calculate_current_cost_basis(
    portfolio: Portfolio,
    security_id: str,
    tax_csv_data: DataFrame[TaxPaidSchema] | None = None,
    evaluation_date: datetime | None = None
) -> Money:
    """
    Calculate current cost basis for a security using FIFO, net of taxes already paid.

    Args:
        portfolio: Portfolio object with all transactions
        security_id: Security to evaluate
        tax_csv_data: Optional CSV with taxes paid per share (if None, returns gross cost basis)
        evaluation_date: Date for evaluation (defaults to today)

    Returns:
        Net cost basis of currently held shares.
        Formula: sum(lot.cost_basis for remaining_lots) - tax_credit
    """
    if evaluation_date is None:
        evaluation_date = datetime.now()

    # Step 1: Get all purchase lots
    purchase_lots = calculate_purchase_lots(portfolio, security_id)
    if purchase_lots.empty:
        log.debug('No purchase lots found for security %s', security_id)
        return 0.0

    # Step 2: Get all sales transactions for this security
    transactions = portfolio.securities_account_transactions
    sales_transactions = transactions[
        transactions.index.get_level_values('securityId') == security_id
    ].pipe(filter_by_type, transaction_types=[TransactionType.SELL, TransactionType.DELIVERY_OUTBOUND])

    # Step 3: Match sales to lots (FIFO)
    remaining_lots = match_sales_to_lots(purchase_lots, sales_transactions)
    if remaining_lots.empty:
        log.debug('All lots for security %s have been sold', security_id)
        return 0.0

    # Step 4: Calculate gross cost basis
    gross_cost_basis = float(remaining_lots['cost_basis'].sum())

    # Step 5: Calculate tax credit (if CSV provided)
    tax_credit = 0.0
    if tax_csv_data is not None:
        tax_credit = calculate_prepaid_tax_for_lots(
            remaining_lots,
            security_id,
            evaluation_date,
            tax_csv_data
        )

    # Step 6: Return net cost basis
    net_cost_basis = max(0.0, gross_cost_basis - tax_credit)
    return net_cost_basis
