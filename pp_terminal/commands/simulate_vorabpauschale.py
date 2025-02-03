"""
    Copyright (C) 2025 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

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
import typer
from typing_extensions import Annotated
import numpy as np

from ..df_filter import filter_by_type, drop_empty_values
from ..helper import get_last_year
from ..output import OutputStrategy, Console
from ..portfolio_snapshot import PortfolioSnapshot
from ..portfolio import Portfolio
from ..schemas import TransactionType, Percent
from ..table_decorator import TableOptions

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
    logging.debug(payouts)

    # @todo convert all values to EUR with rates from ECB, for the moment we simply remove currency
    begin_values_in_eur = snapshot_period_begin.values.groupby(['account_id', 'SecurityId']).sum()
    end_values_in_eur = snapshot_period_end.values.groupby(['account_id', 'SecurityId']).sum()

    # use df.subtract to align both matrices
    outcome = end_values_in_eur.subtract(begin_values_in_eur, fill_value=0)
    outcome.name = 'Outcome'
    logging.debug(outcome)

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


def get_base_rate_percent_by_year() -> Percent | None:
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
        tax_rate: Annotated[Percent, typer.Option(help="Your personal tax rate", min=0, max=100, prompt="Tax Rate (%)", prompt_required=True)] = 0.25 * (1 + 0.055) * 100,
        exemption_rate: Annotated[Percent, typer.Option(help="The default exemption rate (Teilfreistellung), can be overwritten for each security.", min=0, max=100, prompt="Default Exemption Rate (%)", prompt_required=True)] = 30
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

    console.print(*output.result_table(
        result,
        TableOptions(
            title=f"Estimated Taxes on Vorabpauschale {year.year} (§18 InvStG)",
            caption='Actual values will deviate (different security prices), excl. Sparerpauschbetrag',
            show_index=False,
            footer_lines=1
        )
    ))

    console.print(output.warning('For the current version this simulation assumes that all prices are in EUR.'))
