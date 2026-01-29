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
import copy

import pandas as pd
from pandera.typing import DataFrame

from pp_terminal.data.filters import filter_by_type
from pp_terminal.data.tax import calculate_prepaid_tax_for_lots, FifoLot
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import TransactionType, Money, TransactionSchema, TaxPaidSchema, FifoLotSchema

log = logging.getLogger(__name__)


def calculate_purchase_lots(
    portfolio: Portfolio,
    security_id: str,
    sort_by_date: bool = True
) -> list[FifoLot]:
    """
    Get all purchase lots for a security across all accounts.

    Args:
        portfolio: Portfolio object with all transactions
        security_id: Security to get purchase lots for
        sort_by_date: If True, sort lots by purchase date (earliest first) for FIFO

    Returns:
        List of FIFO lots. Each lot includes:
        - purchase_date: Date of purchase
        - account_id: Account holding the lot
        - shares: Number of shares
        - purchase_price: Price per share at purchase
        - cost_basis: Total cost (shares × purchase_price)
        - capital_gain: Initialized to 0.0 (can be set later for sale simulations)
    """
    transactions = portfolio.securities_account_transactions
    purchase_txns = transactions[
        transactions.index.get_level_values('securityId') == security_id
    ].pipe(filter_by_type, transaction_types=[TransactionType.BUY, TransactionType.DELIVERY_INBOUND])

    if purchase_txns.empty:
        log.debug('No purchase transactions found for security %s', security_id)
        return []

    # Build lots from transactions
    lots: list[FifoLot] = []
    for (date, account_id, _), row in purchase_txns.iterrows():
        shares = float(row['shares'])
        if shares <= 0:
            log.warning('Skipping transaction with zero/negative shares: %s', row)
            continue

        # BUY transactions have negative amounts (cash outflow), use absolute value
        purchase_price = abs(float(row['amount']) / shares)
        cost_basis = shares * purchase_price

        lots.append({
            'purchase_date': date,
            'account_id': str(account_id),
            'shares': shares,
            'purchase_price': purchase_price,
            'cost_basis': cost_basis,
            'capital_gain': 0.0  # @todo initialize, can be set later
        })

    # Sort by date if requested (FIFO order)
    if sort_by_date:
        lots.sort(key=lambda lot: lot['purchase_date'])

    return lots


def match_sales_to_lots(
    lots: list[FifoLot],
    sales_transactions: DataFrame[TransactionSchema]
) -> list[FifoLot]:
    """
    Apply FIFO matching of sales to purchase lots.

    Args:
        lots: Purchase lots (should be sorted by date for correct FIFO behavior)
        sales_transactions: DataFrame of SELL + DELIVERY_OUTBOUND transactions

    Returns:
        List of remaining lots after sales are matched.
        Each lot's 'shares' field represents remaining quantity.
        Exhausted lots (shares = 0) are removed.
    """
    if sales_transactions.empty:
        return lots

    # Make deep copy to avoid mutating input
    remaining_lots = copy.deepcopy(lots)

    sales_sorted = sales_transactions.sort_index(level='date')

    for (_date, account_id, _security_id), row in sales_sorted.iterrows():
        shares_to_match = float(row['shares'])

        # Match against lots in FIFO order (only from same account)
        for lot in remaining_lots:
            if shares_to_match <= 0:
                break

            if lot['account_id'] != account_id:
                continue

            # Consume shares from this lot
            shares_from_lot = min(shares_to_match, lot['shares'])
            lot['shares'] -= shares_from_lot
            shares_to_match -= shares_from_lot

            # Also adjust cost_basis proportionally
            if lot['shares'] > 0:
                # Partial lot - reduce cost basis proportionally
                remaining_fraction = lot['shares'] / (lot['shares'] + shares_from_lot)
                lot['cost_basis'] *= remaining_fraction
            else:
                # Lot fully consumed
                lot['cost_basis'] = 0.0

        if shares_to_match > 0.0001:  # Allow small floating point errors
            log.warning('Sale of %.8f shares for security %s could not be fully matched to purchase lots', shares_to_match, _security_id)

    # Filter out exhausted lots
    remaining_lots = [lot for lot in remaining_lots if lot['shares'] > 0.0001]

    return remaining_lots


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
    if not purchase_lots:
        log.debug('No purchase lots found for security %s', security_id)
        return 0.0

    # Step 2: Get all sales transactions for this security
    transactions = portfolio.securities_account_transactions
    sales_transactions = transactions[
        transactions.index.get_level_values('securityId') == security_id
    ].pipe(filter_by_type, transaction_types=[TransactionType.SELL, TransactionType.DELIVERY_OUTBOUND])

    # Step 3: Match sales to lots (FIFO)
    remaining_lots = match_sales_to_lots(purchase_lots, sales_transactions)
    if not remaining_lots:
        log.debug('All lots for security %s have been sold', security_id)
        return 0.0

    # Step 4: Calculate gross cost basis
    gross_cost_basis = sum(lot['cost_basis'] for lot in remaining_lots)

    # Step 5: Calculate tax credit (if CSV provided)
    tax_credit = 0.0
    if tax_csv_data is not None:
        remaining_lots_df = pd.DataFrame(remaining_lots)
        remaining_lots_df['security_id'] = security_id
        remaining_lots_df = FifoLotSchema.validate(remaining_lots_df)
        tax_credit = calculate_prepaid_tax_for_lots(
            remaining_lots_df,
            security_id,
            evaluation_date,
            tax_csv_data
        )

    # Step 6: Return net cost basis
    net_cost_basis = max(0.0, gross_cost_basis - tax_credit)
    return net_cost_basis
