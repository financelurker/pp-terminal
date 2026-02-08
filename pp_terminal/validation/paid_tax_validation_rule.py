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
from typing import Any, cast
import logging
import pandas as pd
from pandera.typing import DataFrame

from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.portfolio_snapshot import PortfolioSnapshot
from pp_terminal.domain.schemas import TaxPaidSchema
from pp_terminal.validation.base import ValidationRule

log = logging.getLogger(__name__)


class PaidTaxValidationRule(ValidationRule):
    """Validates calculated VAP base yield against paid tax data from CSV files."""

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        rule_type: str,
        value: Any,
        severity: str = 'error',
        applies_to: list[str] | None = None,
        *,
        valid_months: list[int] | None = None,
        tolerance: float = 0.1  # tolerance required because of differing asset prices
    ):
        super().__init__(rule_type, value, severity, applies_to, valid_months=valid_months)
        self.tolerance = tolerance

    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:  # pylint: disable=too-many-locals,too-many-branches
        is_error, message = super().validate(entity, entity_id, context)
        if not self._should_apply():
            return is_error, message

        tax_csv_data: DataFrame[TaxPaidSchema] | None = context.get('tax_csv_data')
        base_yield_by_year: dict[int, dict[str, Any]] | None = context.get('base_yield_by_year')
        portfolio = cast(Portfolio, context.get('portfolio'))

        if tax_csv_data is None or tax_csv_data.empty:
            log.debug('Paid tax validation skipped for security %s: no tax CSV data', entity_id)
            return False, None

        if base_yield_by_year is None:
            log.debug('Paid tax validation skipped for security %s: no pre-calculated base yield data', entity_id)
            return False, None

        mismatches = []
        current_year = datetime.now().year

        for year in range(2018, current_year):  # exclude current year
            total_base_yield = base_yield_by_year.get(year, {}).get(entity_id, 0.0)
            snapshot_end = PortfolioSnapshot(portfolio, datetime(year, 12, 31))
            shares = snapshot_end.shares.groupby(level='securityId').sum().to_dict()

            if entity_id in shares and shares[entity_id] > 0:
                calculated_value = total_base_yield
            else:
                calculated_value = 0.0

            if (year, entity_id) in tax_csv_data.index:
                csv_value = float(tax_csv_data.loc[(year, entity_id), 'deemed_income'])
            else:
                csv_value = 0.0

            if not self._within_tolerance(calculated_value, csv_value):
                if csv_value != 0:
                    diff_percent = abs(calculated_value - csv_value) / abs(csv_value) * 100
                else:
                    diff_percent = float('inf') if calculated_value != 0 else 0

                sign = '+' if calculated_value > csv_value else ''
                mismatches.append(f"{year} (calc: {calculated_value:.2f}, csv: {csv_value:.2f}, {sign}{diff_percent:.1f}%)")
            else:
                log.debug('yield values matching for %d: %s vs. %s', year, calculated_value, csv_value)

        if mismatches:
            message = f"has unexpected or missing paid tax values: {', '.join(mismatches)}"
            return self.is_error(), message

        return False, None

    def _within_tolerance(self, calculated: float, csv_value: float) -> bool:
        if csv_value == 0 and calculated == 0:
            return True
        if csv_value == 0:
            return calculated <= self.tolerance
        return abs(calculated - csv_value) / abs(csv_value) <= self.tolerance
