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
# pylint: disable=duplicate-code

from datetime import datetime

import pandas as pd
import pytest

from pp_terminal.data.cost_basis import (
    calculate_purchase_lots,
    match_sales_to_lots,
    calculate_tax_credit_for_lots,
    calculate_current_cost_basis,
    FifoLot
)
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import AccountType, TransactionType


@pytest.fixture(name='portfolio_with_purchases')
def provide_portfolio_with_purchases() -> Portfolio:
    """Portfolio with multiple purchases across two accounts."""
    accounts = pd.DataFrame([
        ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
        ['Account 2', AccountType.SECURITIES.value, None, False, 'EUR'],
    ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'],
       index=['acc-1', 'acc-2'])
    accounts.index.name = 'accountId'

    securities = pd.DataFrame([
        ['Test Security', 'XXX', 'ISIN123', None, False, 'EUR'],
    ], columns=['name', 'wkn', 'isin', 'note', 'isRetired', 'currency'],
       index=['sec-1'])
    securities.index.name = 'securityId'

    # Purchases: BUY amounts are negative (cash outflow)
    transactions = pd.DataFrame([
        [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # 10 shares @ 100
        [datetime(2020, 6, 20), 'acc-1', 'sec-1', TransactionType.BUY.value, -1500.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # 10 shares @ 150
        [datetime(2021, 3, 10), 'acc-2', 'sec-1', TransactionType.DELIVERY_INBOUND.value, 0.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # 5 shares @ 0 (gift)
        [datetime(2022, 1, 5), 'acc-1', 'sec-1', TransactionType.BUY.value, -2000.0, 20.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # 20 shares @ 100
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    transactions = transactions.set_index(['date', 'accountId', 'securityId'])

    return Portfolio(
        accounts=accounts,
        transactions=transactions,
        securities=securities,
        prices=None
    )


@pytest.fixture(name='portfolio_with_sales')
def provide_portfolio_with_sales(portfolio_with_purchases: Portfolio) -> Portfolio:
    """Portfolio with purchases and sales."""
    if not isinstance(portfolio_with_purchases.securities_account_transactions, pd.DataFrame):
        raise TypeError("transactions must be a DataFrame")

    transactions = portfolio_with_purchases.securities_account_transactions.copy()

    # Add sales: SELL amounts are positive (cash inflow)
    sales = pd.DataFrame([
        [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1400.0, 7.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Sell 7 shares
        [datetime(2023, 6, 15), 'acc-2', 'sec-1', TransactionType.DELIVERY_OUTBOUND.value, 0.0, 3.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Transfer out 3 shares
    ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
    sales = sales.set_index(['date', 'accountId', 'securityId'])

    transactions = pd.concat([transactions, sales])

    return Portfolio(
        accounts=portfolio_with_purchases.securities_accounts,
        transactions=transactions,
        securities=portfolio_with_purchases.securities,
        prices=None
    )


@pytest.fixture(name='tax_csv_data')
def provide_tax_csv_data() -> pd.DataFrame:
    """Tax CSV data with taxes paid per share."""
    data = pd.DataFrame([
        [2020, 'acc-1', 'sec-1', 0.05],  # €0.05 per share in 2020
        [2021, 'acc-1', 'sec-1', 0.06],  # €0.06 per share in 2021
        [2021, 'acc-2', 'sec-1', 0.06],  # €0.06 per share in 2021
        [2022, 'acc-1', 'sec-1', 0.07],  # €0.07 per share in 2022
    ], columns=['year', 'account_id', 'security_id', 'tax_per_share'])
    return data.set_index(['year', 'account_id', 'security_id'])


class TestCalculatePurchaseLots:
    """Test calculate_purchase_lots() function."""

    def test_single_purchase(self) -> None:
        """Test with single purchase transaction."""
        accounts = pd.DataFrame([
            ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
        ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
        accounts.index.name = 'accountId'

        securities = pd.DataFrame([
            ['Test Security', 'XXX', 'ISIN123', None, False, 'EUR'],
        ], columns=['name', 'wkn', 'isin', 'note', 'isRetired', 'currency'], index=['sec-1'])
        securities.index.name = 'securityId'

        transactions = pd.DataFrame([
            [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0],
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        transactions = transactions.set_index(['date', 'accountId', 'securityId'])

        portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=securities, prices=None)

        lots = calculate_purchase_lots(portfolio, 'sec-1')

        assert len(lots) == 1
        assert lots[0]['account_id'] == 'acc-1'
        assert lots[0]['shares'] == 10.0
        assert lots[0]['purchase_price'] == 100.0
        assert lots[0]['cost_basis'] == 1000.0

    def test_multiple_purchases_sorted_by_date(self, portfolio_with_purchases: Portfolio) -> None:
        """Test that multiple purchases are sorted by date (FIFO order)."""
        lots = calculate_purchase_lots(portfolio_with_purchases, 'sec-1', sort_by_date=True)

        assert len(lots) == 4
        assert lots[0]['purchase_date'] == datetime(2020, 1, 15)
        assert lots[1]['purchase_date'] == datetime(2020, 6, 20)
        assert lots[2]['purchase_date'] == datetime(2021, 3, 10)
        assert lots[3]['purchase_date'] == datetime(2022, 1, 5)

    def test_multiple_accounts(self, portfolio_with_purchases: Portfolio) -> None:
        """Test purchases across multiple accounts."""
        lots = calculate_purchase_lots(portfolio_with_purchases, 'sec-1')

        acc1_lots = [lot for lot in lots if lot['account_id'] == 'acc-1']
        acc2_lots = [lot for lot in lots if lot['account_id'] == 'acc-2']

        assert len(acc1_lots) == 3
        assert len(acc2_lots) == 1

    def test_delivery_inbound_included(self, portfolio_with_purchases: Portfolio) -> None:
        """Test that DELIVERY_INBOUND transactions are included."""
        lots = calculate_purchase_lots(portfolio_with_purchases, 'sec-1')

        delivery_lot = [lot for lot in lots if lot['purchase_date'] == datetime(2021, 3, 10)][0]
        assert delivery_lot['shares'] == 5.0
        assert delivery_lot['purchase_price'] == 0.0
        assert delivery_lot['cost_basis'] == 0.0

    def test_no_transactions(self) -> None:
        """Test with portfolio that has no transactions."""
        accounts = pd.DataFrame([
            ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
        ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
        accounts.index.name = 'accountId'

        portfolio = Portfolio(accounts=accounts, transactions=None, securities=None, prices=None)

        lots = calculate_purchase_lots(portfolio, 'sec-1')

        assert len(lots) == 0

    def test_no_purchases_for_security(self, portfolio_with_purchases: Portfolio) -> None:
        """Test with security that has no purchases."""
        lots = calculate_purchase_lots(portfolio_with_purchases, 'non-existent-security')

        assert len(lots) == 0

    def test_zero_shares_skipped(self) -> None:
        """Test that transactions with zero shares are skipped."""
        accounts = pd.DataFrame([
            ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
        ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
        accounts.index.name = 'accountId'

        securities = pd.DataFrame([
            ['Test Security', 'XXX', 'ISIN123', None, False, 'EUR'],
        ], columns=['name', 'wkn', 'isin', 'note', 'isRetired', 'currency'], index=['sec-1'])
        securities.index.name = 'securityId'

        transactions = pd.DataFrame([
            [datetime(2020, 1, 15), 'acc-1', 'sec-1', TransactionType.BUY.value, -1000.0, 0.0, AccountType.SECURITIES.value, 'EUR', 0.0],
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        transactions = transactions.set_index(['date', 'accountId', 'securityId'])

        portfolio = Portfolio(accounts=accounts, transactions=transactions, securities=securities, prices=None)

        lots = calculate_purchase_lots(portfolio, 'sec-1')

        assert len(lots) == 0


class TestMatchSalesToLots:
    """Test match_sales_to_lots() function."""

    def test_partial_lot_consumption(self) -> None:
        """Test that sales partially consume lots in FIFO order."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 15),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 100.0,
                'cost_basis': 1000.0,
                'capital_gain': 0.0
            },
            {
                'purchase_date': datetime(2020, 6, 20),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 150.0,
                'cost_basis': 1500.0,
                'capital_gain': 0.0
            }
        ]

        sales = pd.DataFrame([
            [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1400.0, 7.0, AccountType.SECURITIES.value, 'EUR', 0.0],
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        sales = sales.set_index(['date', 'accountId', 'securityId'])

        remaining_lots = match_sales_to_lots(lots, sales)

        # Sale of 7 shares consumes 7 from first lot (10 shares), leaving 3 shares in first lot
        # Second lot (10 shares) remains untouched
        assert len(remaining_lots) == 2
        assert remaining_lots[0]['shares'] == pytest.approx(3.0, abs=0.0001)
        assert remaining_lots[0]['cost_basis'] == pytest.approx(300.0, abs=0.01)
        assert remaining_lots[1]['shares'] == pytest.approx(10.0, abs=0.0001)
        assert remaining_lots[1]['cost_basis'] == pytest.approx(1500.0, abs=0.01)

    def test_full_lot_consumption(self) -> None:
        """Test that sales fully consume lots."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 15),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 100.0,
                'cost_basis': 1000.0,
                'capital_gain': 0.0
            }
        ]

        sales = pd.DataFrame([
            [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 2000.0, 10.0, AccountType.SECURITIES.value, 'EUR', 0.0],
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        sales = sales.set_index(['date', 'accountId', 'securityId'])

        remaining_lots = match_sales_to_lots(lots, sales)

        assert len(remaining_lots) == 0

    def test_multiple_sales_fifo_order(self) -> None:
        """Test that multiple sales consume lots in FIFO order."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 15),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 100.0,
                'cost_basis': 1000.0,
                'capital_gain': 0.0
            },
            {
                'purchase_date': datetime(2020, 6, 20),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 150.0,
                'cost_basis': 1500.0,
                'capital_gain': 0.0
            },
            {
                'purchase_date': datetime(2022, 1, 5),
                'account_id': 'acc-1',
                'shares': 20.0,
                'purchase_price': 100.0,
                'cost_basis': 2000.0,
                'capital_gain': 0.0
            }
        ]

        sales = pd.DataFrame([
            [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1400.0, 7.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Consume 7 from lot 1
            [datetime(2023, 6, 15), 'acc-1', 'sec-1', TransactionType.SELL.value, 1800.0, 12.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Consume 3 from lot 1, 9 from lot 2
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        sales = sales.set_index(['date', 'accountId', 'securityId'])

        remaining_lots = match_sales_to_lots(lots, sales)

        # Lot 1 (10 shares): 7 sold in first sale, 3 sold in second sale -> fully consumed
        # Lot 2 (10 shares): 9 sold in second sale -> 1 share remaining
        # Lot 3 (20 shares): untouched
        assert len(remaining_lots) == 2
        assert remaining_lots[0]['shares'] == pytest.approx(1.0, abs=0.0001)
        assert remaining_lots[1]['shares'] == pytest.approx(20.0, abs=0.0001)

    def test_no_sales(self) -> None:
        """Test with no sales (all lots remain)."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 15),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 100.0,
                'cost_basis': 1000.0,
                'capital_gain': 0.0
            }
        ]

        sales = pd.DataFrame(columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        sales = sales.set_index(['date', 'accountId', 'securityId'])

        remaining_lots = match_sales_to_lots(lots, sales)

        assert len(remaining_lots) == 1
        assert remaining_lots[0]['shares'] == 10.0

    def test_delivery_outbound_included(self) -> None:
        """Test that DELIVERY_OUTBOUND transactions are included in sales."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 15),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 100.0,
                'cost_basis': 1000.0,
                'capital_gain': 0.0
            }
        ]

        sales = pd.DataFrame([
            [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.DELIVERY_OUTBOUND.value, 0.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0],
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        sales = sales.set_index(['date', 'accountId', 'securityId'])

        remaining_lots = match_sales_to_lots(lots, sales)

        assert len(remaining_lots) == 1
        assert remaining_lots[0]['shares'] == pytest.approx(5.0, abs=0.0001)

    def test_lots_not_mutated(self) -> None:
        """Test that original lots are not mutated (deep copy)."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 15),
                'account_id': 'acc-1',
                'shares': 10.0,
                'purchase_price': 100.0,
                'cost_basis': 1000.0,
                'capital_gain': 0.0
            }
        ]

        sales = pd.DataFrame([
            [datetime(2020, 12, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 1000.0, 5.0, AccountType.SECURITIES.value, 'EUR', 0.0],
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        sales = sales.set_index(['date', 'accountId', 'securityId'])

        original_shares = lots[0]['shares']
        match_sales_to_lots(lots, sales)

        assert lots[0]['shares'] == original_shares  # Original not mutated


class TestCalculateTaxCreditForLots:
    """Test calculate_tax_credit_for_lots() function."""

    def test_single_year_full_year(self, tax_csv_data: pd.DataFrame) -> None:
        """Test tax credit for single lot held full year."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 1),
                'account_id': 'acc-1',
                'shares': 100.0,
                'purchase_price': 100.0,
                'cost_basis': 10000.0,
                'capital_gain': 0.0
            }
        ]

        # Current date 2022-12-31: years held = 2020, 2021 (not 2022 because last_year = current_year - 1)
        current_date = datetime(2022, 12, 31)
        credit = calculate_tax_credit_for_lots(lots, 'sec-1', current_date, tax_csv_data)

        # 2020: 100 shares * €0.05 = €5.00 (full year)
        # 2021: 100 shares * €0.06 = €6.00 (full year)
        # Total: €11.00
        assert credit == pytest.approx(11.0, abs=0.01)

    def test_purchase_year_month_proration(self, tax_csv_data: pd.DataFrame) -> None:
        """Test that purchase year is prorated by months held."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 6, 15),  # June = month 6
                'account_id': 'acc-1',
                'shares': 100.0,
                'purchase_price': 100.0,
                'cost_basis': 10000.0,
                'capital_gain': 0.0
            }
        ]

        current_date = datetime(2022, 12, 31)
        credit = calculate_tax_credit_for_lots(lots, 'sec-1', current_date, tax_csv_data)

        # 2020: 100 shares * €0.05 * (13-6)/12 = 100 * 0.05 * 7/12 = €2.92
        # 2021: 100 shares * €0.06 * 1.0 = €6.00
        # Total: €8.92
        assert credit == pytest.approx(8.92, abs=0.01)

    def test_multiple_lots_different_accounts(self, tax_csv_data: pd.DataFrame) -> None:
        """Test tax credit across multiple lots in different accounts."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 1),
                'account_id': 'acc-1',
                'shares': 50.0,
                'purchase_price': 100.0,
                'cost_basis': 5000.0,
                'capital_gain': 0.0
            },
            {
                'purchase_date': datetime(2021, 1, 1),
                'account_id': 'acc-2',
                'shares': 30.0,
                'purchase_price': 120.0,
                'cost_basis': 3600.0,
                'capital_gain': 0.0
            }
        ]

        current_date = datetime(2022, 12, 31)
        credit = calculate_tax_credit_for_lots(lots, 'sec-1', current_date, tax_csv_data)

        # Lot 1 (acc-1):
        #   2020: 50 * €0.05 = €2.50
        #   2021: 50 * €0.06 = €3.00
        # Lot 2 (acc-2):
        #   2021: 30 * €0.06 = €1.80
        # Total: €7.30
        assert credit == pytest.approx(7.30, abs=0.01)

    def test_purchased_in_current_year_no_credit(self, tax_csv_data: pd.DataFrame) -> None:
        """Test that lots purchased in current year have no tax credit."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2022, 6, 1),
                'account_id': 'acc-1',
                'shares': 100.0,
                'purchase_price': 100.0,
                'cost_basis': 10000.0,
                'capital_gain': 0.0
            }
        ]

        current_date = datetime(2022, 12, 31)
        credit = calculate_tax_credit_for_lots(lots, 'sec-1', current_date, tax_csv_data)

        # Purchased in 2022, evaluated in 2022 -> last_year = 2021 < first_year = 2022
        assert credit == 0.0

    def test_missing_tax_data_ignored(self, tax_csv_data: pd.DataFrame) -> None:
        """Test that missing tax data for year/account/security is ignored (returns 0)."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2019, 1, 1),
                'account_id': 'acc-1',
                'shares': 100.0,
                'purchase_price': 100.0,
                'cost_basis': 10000.0,
                'capital_gain': 0.0
            }
        ]

        current_date = datetime(2022, 12, 31)
        credit = calculate_tax_credit_for_lots(lots, 'sec-1', current_date, tax_csv_data)

        # 2019: No data in CSV -> €0.00
        # 2020: 100 * €0.05 = €5.00
        # 2021: 100 * €0.06 = €6.00
        # Total: €11.00 (2019 silently ignored)
        assert credit == pytest.approx(11.0, abs=0.01)

    def test_no_tax_csv_returns_zero(self) -> None:
        """Test that None tax CSV returns zero credit."""
        lots: list[FifoLot] = [
            {
                'purchase_date': datetime(2020, 1, 1),
                'account_id': 'acc-1',
                'shares': 100.0,
                'purchase_price': 100.0,
                'cost_basis': 10000.0,
                'capital_gain': 0.0
            }
        ]

        current_date = datetime(2022, 12, 31)
        credit = calculate_tax_credit_for_lots(lots, 'sec-1', current_date, None)

        assert credit == 0.0


class TestCalculateCurrentCostBasis:
    """Test calculate_current_cost_basis() function (end-to-end)."""

    def test_only_purchases_no_sales(self, portfolio_with_purchases: Portfolio) -> None:
        """Test cost basis with only purchases (no sales)."""
        cost_basis = calculate_current_cost_basis(portfolio_with_purchases, 'sec-1')

        # Lot 1: 10 shares @ €100 = €1,000
        # Lot 2: 10 shares @ €150 = €1,500
        # Lot 3: 5 shares @ €0 = €0
        # Lot 4: 20 shares @ €100 = €2,000
        # Total: €4,500
        assert cost_basis == pytest.approx(4500.0, abs=0.01)

    def test_purchases_and_sales(self, portfolio_with_sales: Portfolio) -> None:
        """Test cost basis with purchases and sales (FIFO matching)."""
        cost_basis = calculate_current_cost_basis(portfolio_with_sales, 'sec-1')

        # Purchases:
        #   2020-01-15: acc-1, 10 shares @ €100 = €1,000
        #   2020-06-20: acc-1, 10 shares @ €150 = €1,500
        #   2021-03-10: acc-2, 5 shares @ €0 = €0
        #   2022-01-05: acc-1, 20 shares @ €100 = €2,000
        # Sales:
        #   2020-12-01: acc-1, 7 shares (consumes 7 from lot 1)
        #   2023-06-15: acc-2, 3 shares (consumes 3 from lot 3)
        # Remaining:
        #   Lot 1: 3 shares @ €100 = €300
        #   Lot 2: 10 shares @ €150 = €1,500
        #   Lot 3: 2 shares @ €0 = €0
        #   Lot 4: 20 shares @ €100 = €2,000
        # Total: €3,800
        assert cost_basis == pytest.approx(3800.0, abs=0.01)

    def test_with_tax_credit(self, portfolio_with_purchases: Portfolio, tax_csv_data: pd.DataFrame) -> None:
        """Test cost basis net of tax credit."""
        evaluation_date = datetime(2022, 12, 31)
        cost_basis = calculate_current_cost_basis(
            portfolio_with_purchases,
            'sec-1',
            tax_csv_data=tax_csv_data,
            evaluation_date=evaluation_date
        )

        # Gross cost basis: €4,500 (from test_only_purchases_no_sales)
        # Tax credit calculation:
        #   Lot 1 (2020-01-15, acc-1, 10 shares):
        #     2020: 10 * €0.05 * (13-1)/12 = €0.50
        #     2021: 10 * €0.06 = €0.60
        #   Lot 2 (2020-06-20, acc-1, 10 shares):
        #     2020: 10 * €0.05 * (13-6)/12 = €0.29
        #     2021: 10 * €0.06 = €0.60
        #   Lot 3 (2021-03-10, acc-2, 5 shares):
        #     2021: 5 * €0.06 * (13-3)/12 = €0.25
        #   Lot 4 (2022-01-05, acc-1, 20 shares):
        #     No credit (purchased in 2022, evaluated in 2022)
        # Total tax credit: €2.24
        # Net cost basis: €4,500 - €2.24 = €4,497.76
        expected_credit = (
            10 * 0.05 * (13-1)/12 +  # Lot 1, 2020
            10 * 0.06 +               # Lot 1, 2021
            10 * 0.05 * (13-6)/12 +  # Lot 2, 2020
            10 * 0.06 +               # Lot 2, 2021
            5 * 0.06 * (13-3)/12      # Lot 3, 2021
        )
        assert cost_basis == pytest.approx(4500.0 - expected_credit, abs=0.01)

    def test_all_shares_sold(self, portfolio_with_sales: Portfolio) -> None:
        """Test that cost basis is zero when all shares are sold."""
        if not isinstance(portfolio_with_sales.securities_account_transactions, pd.DataFrame):
            raise TypeError('transactions must be a DataFrame')

        # Add more sales to sell everything
        transactions = portfolio_with_sales.securities_account_transactions.copy()

        more_sales = pd.DataFrame([
            [datetime(2024, 1, 1), 'acc-1', 'sec-1', TransactionType.SELL.value, 5000.0, 33.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Sell remaining 33 shares
            [datetime(2024, 1, 2), 'acc-2', 'sec-1', TransactionType.SELL.value, 0.0, 2.0, AccountType.SECURITIES.value, 'EUR', 0.0],  # Sell remaining 2 from acc-2
        ], columns=['date', 'accountId', 'securityId', 'type', 'amount', 'shares', 'accountType', 'currency', 'taxes'])
        more_sales = more_sales.set_index(['date', 'accountId', 'securityId'])

        transactions = pd.concat([transactions, more_sales])

        portfolio = Portfolio(
            accounts=portfolio_with_sales.securities_accounts,
            transactions=transactions,
            securities=portfolio_with_sales.securities,
            prices=None
        )

        cost_basis = calculate_current_cost_basis(portfolio, 'sec-1')

        assert cost_basis == 0.0

    def test_no_transactions(self) -> None:
        """Test with portfolio that has no transactions."""
        accounts = pd.DataFrame([
            ['Account 1', AccountType.SECURITIES.value, None, False, 'EUR'],
        ], columns=['name', 'type', 'referenceAccount', 'isRetired', 'currency'], index=['acc-1'])
        accounts.index.name = 'accountId'

        portfolio = Portfolio(accounts=accounts, transactions=None, securities=None, prices=None)

        cost_basis = calculate_current_cost_basis(portfolio, 'sec-1')

        assert cost_basis == 0.0

    def test_no_purchases_for_security(self, portfolio_with_purchases: Portfolio) -> None:
        """Test with security that has no purchases."""
        cost_basis = calculate_current_cost_basis(portfolio_with_purchases, 'non-existent-security')

        assert cost_basis == 0.0

    def test_net_cost_basis_not_negative(self, portfolio_with_purchases: Portfolio) -> None:
        """Test that net cost basis is capped at 0 (not negative)."""
        # Create tax CSV with very high tax credits
        high_tax_csv = pd.DataFrame([
            [2020, 'acc-1', 'sec-1', 500.0],  # €500 per share (unrealistically high)
        ], columns=['year', 'account_id', 'security_id', 'tax_per_share'])
        high_tax_csv = high_tax_csv.set_index(['year', 'account_id', 'security_id'])

        evaluation_date = datetime(2022, 12, 31)
        cost_basis = calculate_current_cost_basis(
            portfolio_with_purchases,
            'sec-1',
            tax_csv_data=high_tax_csv,
            evaluation_date=evaluation_date
        )

        # Cost basis should be capped at 0, not negative
        assert cost_basis == 0.0
