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
from typing import Any

import pandas as pd
import typer
from typing_extensions import Annotated
import numpy as np

from ..df_filter import filter_by_type, drop_empty_values
from ..helper import get_last_year, footer
from ..options import tax_rate_callback, exemption_rate_callback
from ..output import OutputStrategy, Console
from ..portfolio_snapshot import PortfolioSnapshot, _NEGATIVE_SECURITIES_ACCOUNT_TRANSACTION_TYPES
from ..portfolio import Portfolio
from ..schemas import TransactionType, Percent, Money
from ..table_decorator import TableOptions, format_value

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)

begin = None  # pylint: disable=invalid-name


# @see https://www.gesetze-im-internet.de/invstg_2018/__18.html
def calculate(  # pylint: disable=too-many-locals
        snapshot_period_begin: PortfolioSnapshot,
        snapshot_period_end: PortfolioSnapshot,
        base_rate_percent: Percent,
        tax_rate_percent: Percent,
        default_exemption_rate_percent: Percent = 30.0
) -> pd.DataFrame | None:
    base_rate = max(base_rate_percent, 0) / 100

    payouts = _calculate_payouts(snapshot_period_end)
    log.debug(payouts)

    # @todo convert all values to EUR with rates from ECB, for the moment we simply remove currency
    # Calculate begin values only for shares held continuously from year start to year end
    shares_begin = snapshot_period_begin.shares
    shares_end = snapshot_period_end.shares

    if shares_begin is not None and shares_end is not None and not shares_begin.empty and not shares_end.empty:
        # Calculate minimum position during the year to detect complete sells
        min_shares_during_year = _calculate_minimum_shares_during_year(snapshot_period_end)

        if min_shares_during_year is not None:
            # Only count shares held continuously (never went to zero)
            effective_begin_shares = shares_begin.combine(min_shares_during_year, min, fill_value=0).clip(lower=0)
        else:
            # Fallback: cap by end shares (assumes continuous holding)
            effective_begin_shares = shares_begin.combine(shares_end, min, fill_value=0).clip(lower=0)

        effective_begin_shares.name = 'Shares'

        # Calculate begin values using continuously held shares
        begin_values_in_eur = (snapshot_period_begin.latest_prices * effective_begin_shares).groupby(['account_id', 'SecurityId']).sum()
    else:
        begin_values_in_eur = snapshot_period_begin.values.groupby(['account_id', 'SecurityId']).sum()

    end_values_in_eur = snapshot_period_end.values.groupby(['account_id', 'SecurityId']).sum()

    # use df.subtract to align both matrices
    outcome = end_values_in_eur.subtract(begin_values_in_eur, fill_value=0)
    outcome.name = 'Outcome'
    log.debug(outcome)

    # for securities that have been bought within the year we need to take the number of months held into account
    pro_rata_shares = _calculate_prorata_shares_for_inyear_buys(snapshot_period_end)
    modified_values_begin = begin_values_in_eur.add(pro_rata_shares.mul(snapshot_period_begin.latest_prices, fill_value=0), fill_value=0) if pro_rata_shares is not None else snapshot_period_begin.values

    base_yield = modified_values_begin * base_rate * 0.7
    base_yield = outcome.combine(base_yield, np.minimum)
    base_yield.name = 'Base Yield'
    logging.debug(base_yield)

    vorabpauschale = base_yield.subtract(payouts, fill_value=0) if payouts is not None else base_yield
    vorabpauschale = vorabpauschale.clip(lower=0).fillna(0)  # replace negative values with zero

    vorabpauschale = vorabpauschale * tax_rate_percent / 100

    if snapshot_period_end.portfolio.securities is not None and 'exempt_rate' in snapshot_period_end.portfolio.securities.columns:
        exempt_rate_per_security = (1 - snapshot_period_end.portfolio.securities[['exempt_rate']]
                                    .astype(float)
                                    .fillna(default_exemption_rate_percent / 100)
                                    .rename(columns={'exempt_rate': 0}))  # column name must match vorabpauschale
        vorabpauschale = exempt_rate_per_security.mul(vorabpauschale.to_frame(), level='SecurityId')

    if not vorabpauschale.empty:
        vorabpauschale = vorabpauschale.unstack(level='account_id')
        vorabpauschale.columns = [col[1] if len(col) > 1 else col[0] for col in vorabpauschale.columns]

    vorabpauschale = vorabpauschale.pipe(drop_empty_values)
    if vorabpauschale.empty or snapshot_period_end.portfolio.securities is None or snapshot_period_end.portfolio.securities_accounts is None:
        return None

    vorabpauschale = pd.merge(snapshot_period_end.portfolio.securities[['Wkn', 'Name', 'currency']], vorabpauschale, left_index=True, right_index=True, how='right').sort_values(by='Name')

    securities_accounts = snapshot_period_end.portfolio.securities_accounts
    if securities_accounts is not None and 'Referenceaccount_id' in securities_accounts and snapshot_period_end.balances is not None:
        # add the reference account balance
        vorabpauschale.loc[len(vorabpauschale)] = (pd.merge(securities_accounts, snapshot_period_end.balances.groupby(['account_id']).sum(), left_on='Referenceaccount_id', right_index=True, how='left')['Balance'].dropna().to_dict()
                                                   | {'Name': 'Related Account Balance', 'currency': snapshot_period_end.portfolio.base_currency})

    return vorabpauschale.rename(columns=securities_accounts['Name'])


def _calculate_payouts(snapshot_end: PortfolioSnapshot) -> pd.Series | None:
    transactions = snapshot_end.transactions
    if transactions is None:
        return None

    transactions = transactions[transactions.index.get_level_values('date').year == snapshot_end.date.year] if not transactions.index.get_level_values('date').empty else transactions

    payouts = transactions.pipe(filter_by_type, transaction_types=TransactionType.DIVIDENDS).groupby(['account_id', 'SecurityId'])['amount'].sum()
    payouts.name = 'Payouts'

    return payouts


def _calculate_minimum_shares_during_year(snapshot_end: PortfolioSnapshot) -> pd.Series | None:  # pylint: disable=too-many-locals
    """
    Calculate the minimum share position during the tax year for each security.
    This detects if a position went to zero (complete sell) and was then rebought.
    Returns minimum shares held at any point during the year.
    """
    transactions = snapshot_end.transactions
    if transactions is None:
        return None

    # Get year-start position
    year_start = datetime(snapshot_end.date.year, 1, 2)
    snapshot_begin = PortfolioSnapshot(snapshot_end.portfolio, year_start)
    begin_shares = snapshot_begin.shares

    if begin_shares is None or begin_shares.empty:
        # No position at year start, minimum is 0 for all
        return None

    # Get only in-year transactions
    transactions_inyear = transactions[
        transactions.index.get_level_values('date').year == snapshot_end.date.year
    ] if not transactions.index.get_level_values('date').empty else pd.DataFrame()

    if transactions_inyear.empty:
        # No transactions during year, minimum = begin shares
        return begin_shares

    # Calculate cumulative changes during the year
    def sign_shares(row: pd.Series) -> float:
        return float(-row['Shares'] if row['Type'] in [t.value for t in _NEGATIVE_SECURITIES_ACCOUNT_TRANSACTION_TYPES] else row['Shares'])

    # Group by account/security and calculate minimum cumulative position
    result_dict = {}

    for (account_id, security_id, currency), begin_count in begin_shares.items():
        # Get transactions for this specific account/security
        mask = (
            (transactions_inyear.index.get_level_values('account_id') == account_id) &
            (transactions_inyear.index.get_level_values('SecurityId') == security_id)
        )
        security_txns = transactions_inyear[mask].copy() if mask.any() else pd.DataFrame()

        if security_txns.empty:
            # No transactions, min = begin
            result_dict[(account_id, security_id, currency)] = begin_count
        else:
            # Calculate cumulative position starting from begin_count
            security_txns = security_txns.reset_index().sort_values('date')
            security_txns['signed_shares'] = security_txns.apply(sign_shares, axis=1)
            cumulative = begin_count + security_txns['signed_shares'].cumsum()
            min_position = min(begin_count, cumulative.min())
            result_dict[(account_id, security_id, currency)] = max(0, min_position)

    if not result_dict:
        return None

    index = pd.MultiIndex.from_tuples(result_dict.keys(), names=['account_id', 'SecurityId', 'currency'])
    return pd.Series(list(result_dict.values()), index=index, name='MinShares')


def _calculate_prorata_shares_for_inyear_buys(snapshot_end: PortfolioSnapshot) -> pd.Series | None:
    transactions = snapshot_end.transactions
    if transactions is None:
        return None

    transactions_inyear = transactions[transactions.index.get_level_values('date').year == snapshot_end.date.year] if not transactions.index.get_level_values('date').empty else None
    if transactions_inyear is None:
        return pd.Series([], name='amount', index=pd.MultiIndex.from_tuples([], names=['account_id', 'SecurityId']), dtype='float64')

    transactions_inyear = transactions_inyear.pipe(filter_by_type, transaction_types=[TransactionType.BUY, TransactionType.DELIVERY_INBOUND])
    transactions_inyear['months_held'] = snapshot_end.date.month - transactions_inyear.index.get_level_values('date').month + 1
    transactions_inyear['shares_original'] = transactions_inyear['Shares']
    transactions_inyear['Shares'] = transactions_inyear['Shares'] * transactions_inyear['months_held']/12
    log.debug(transactions_inyear[['shares_original', 'months_held', 'Shares']].reset_index(level='date', drop=True).sort_values(by=['account_id', 'SecurityId', 'months_held']))

    return transactions_inyear.groupby(['account_id', 'SecurityId'])['Shares'].sum().abs()


def set_begin(value: datetime | None) -> datetime | None:
    """
    Temporary store the non-empty year / datetime in a global state.
    This is necessary because typer.default_factory does not have context available to make one option dependent on the other.
    """
    global begin  # pylint: disable=global-statement

    if value is not None:
        begin = value

    return value


def get_base_rate_percent_by_year() -> Percent | None:  # this has to be adapted every year
    if begin is None:
        return None

    match begin.year:
        case 2016:
            rate = 1.1
        case 2018:
            rate = 0.87
        case 2019:
            rate = 0.52
        case 2020:
            rate = 0.07
        case 2021:
            rate = -0.45
        case 2022:
            rate = -0.05
        case 2023:
            rate = 2.55
        case 2024:
            rate = 2.29
        case 2025:
            rate = 2.53
        case _:
            rate = 2.53

    return rate


@app.command(name="vorabpauschale")
def print_tax_table(
        ctx: typer.Context,
        year: Annotated[datetime, typer.Option(formats=["%Y"], help="The year to calculate the preliminary tax for", prompt=True, callback=set_begin, default_factory=get_last_year)],
        base_rate: Annotated[Percent, typer.Option(help="The base rate (Basiszinssatz)", min=-100, max=100, prompt="Base Rate (%)", prompt_required=True, default_factory=get_base_rate_percent_by_year)],
        tax_rate: Annotated[Percent, typer.Option(help="Your personal tax rate", min=0, max=100, callback=tax_rate_callback)] = None,  # type: ignore
        exemption_rate: Annotated[Percent, typer.Option(help="The default exemption rate (Teilfreistellung), can be overwritten for each security.", min=0, max=100, callback=exemption_rate_callback)] = None  # type: ignore
) -> None:
    """
    Print a detailed table with calculated German preliminary tax values ("Vorabpauschale") for a specified year, per each security and account.
    """

    portfolio = ctx.obj.portfolio  # type: Portfolio
    output = ctx.obj.output  # type: OutputStrategy

    console.print(output.hint('You can define the exemption rate for each security individually by creating a custom security attribute with a name like "Teilfreistellung" of type "Percent Number" in Portfolio Performance.'))

    snapshot_begin = PortfolioSnapshot(portfolio, datetime(year.year, 1, 2))
    snapshot_end = PortfolioSnapshot(portfolio, datetime(year.year, 12, 31))

    result = calculate(snapshot_begin, snapshot_end, base_rate, tax_rate, exemption_rate)
    result = result.round(2) if result is not None else result

    vorabpauschale_totals = {}
    if result is not None and not result.empty:
        balance_row_index = result[result['Name'] == 'Related Account Balance'].index
        if len(balance_row_index) > 0:
            vorabpauschale_data = result.drop(balance_row_index)
            account_columns = [col for col in result.columns if col not in ['Wkn', 'Name', 'currency']]
            vorabpauschale_totals = vorabpauschale_data[account_columns].sum().to_dict()

    def format_value_with_balance_check(value: Any, index: str, row: pd.Series) -> str:
        if 'Name' in row.index and row['Name'] == 'Related Account Balance' and isinstance(value, Money) and index in vorabpauschale_totals:
            color = 'red' if value < vorabpauschale_totals[index] else 'green'
            return f"[{color}]{format_value(value, index, row)}[/{color}]"
        return format_value(value, index, row)

    console.print(*output.result_table(
        result,
        TableOptions(
            title=f"Estimated Taxes on Vorabpauschale {year.year} (§18 InvStG)",
            show_index=False,
            footer_lines=1,
            value_formatter=format_value_with_balance_check
        )
    ))

    console.print(output.warning('This simulation assumes that all amounts are in EUR excl. Sparerpauschbetrag.'))
    console.print(output.text(footer()), style="dim")
