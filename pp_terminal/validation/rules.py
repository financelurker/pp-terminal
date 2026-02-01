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

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, cast
import logging
import pandas as pd
from pandera.typing import DataFrame

from pp_terminal.data.cost_basis import calculate_total_cost_basis
from pp_terminal.data.tax import load_prepaid_tax_data_from_csv
from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.schemas import TaxPaidSchema

log = logging.getLogger(__name__)


class ValidationRule(ABC):
    def __init__(
        self,
        rule_type: str,
        value: Any,
        severity: str = 'error',
        applies_to: list[str] | None = None
    ):
        self.rule_type = rule_type
        self._value = value
        self.severity = severity
        self.applies_to = applies_to

    @abstractmethod
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate entity and return (is_error, message) tuple.

        Returns:
            tuple[bool, str | None]:
                - First element: True if error occurred (severity='error' and validation failed)
                - Second element: Violation message if validation failed, None otherwise
        """
        log.debug('Validating %s of "%s" (%s) using value %s %s', str(self), entity["name"], entity_id, str(self._get_value(entity)), '(' + str(self._value) + ')' if self._value != self._get_value(entity) else '')

        return (False, None)

    def matches_entity(self, entity: pd.Series, entity_id: str) -> bool:
        if self.rule_type.endswith('-from-attribute'):
            attr_uuid = self._value
            return attr_uuid in entity.index and pd.notna(entity.get(attr_uuid))

        if self.applies_to is not None:
            return entity_id in self.applies_to

        return True

    def _get_value(self, entity: pd.Series) -> Any:
        if self.rule_type.endswith('-from-attribute'):
            attr_uuid = self._value
            return entity.get(attr_uuid)
        return self._value

    def log_violation(self, message: str) -> None:
        if self.severity == 'error':
            log.error(message)
        else:
            log.warning(message)

    def is_error(self) -> bool:
        return bool(self.severity == 'error')

    def __str__(self) -> str:
        return self.rule_type


class BalanceLimitRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        limit = self._get_value(entity)
        balance = context['balance']

        if balance > limit:
            message = f'balance {balance:.2f} exceeds limit {limit:.2f}'
            return self.is_error(), message
        return False, None


class DatePassedRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        date_value = self._get_value(entity)

        if pd.isna(date_value):
            return False, None

        if not isinstance(date_value, datetime):
            try:
                date_value = pd.to_datetime(date_value)
            except (ValueError, TypeError):
                log.warning('"%s" has invalid date value: %s', entity["name"], date_value)
                return False, None

        attribute_name = 'date attribute'
        portfolio = cast(Portfolio, context.get('portfolio')) if context else None
        if portfolio is not None:
            attribute_name = portfolio.all_attributes.get(self._value, attribute_name)

        current_date = datetime.now()
        if date_value < current_date:
            message = f'{attribute_name} has passed {date_value.strftime("%Y-%m-%d")}'
            return self.is_error(), message
        return False, None


class PriceStalenessRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        max_days = self._get_value(entity)
        latest_price_date = context.get('latest_price_date')

        if pd.isna(latest_price_date) or latest_price_date is None:
            message = 'no price data'
            return self.is_error(), message

        current_date = datetime.now()
        days_old = (current_date - latest_price_date).days

        if days_old > max_days:
            message = f'price is {days_old} days old (latest: {latest_price_date.strftime("%Y-%m-%d")})'
            return self.is_error(), message
        return False, None


class PriceLimitRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        limit = self._get_value(entity)
        current_price = context.get('current_price')

        if pd.isna(current_price):
            message = 'no price data'
            return self.is_error(), message

        if current_price >= limit:
            message = f'price {current_price:.2f} has reached limit {limit:.2f}'
            return self.is_error(), message
        return False, None


class PurchaseCostLimitRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        limit = self._get_value(entity)
        portfolio = cast(Portfolio, context.get('portfolio'))

        if portfolio is None:
            raise RuntimeError('No portfolio in context for purchase-cost-limit validation')

        transactions = portfolio.securities_account_transactions
        current_cost = calculate_total_cost_basis(transactions, entity_id)

        if current_cost > limit:
            currency = entity.get('currency', 'EUR')
            message = f'current cost basis {current_cost:.2f} {currency} exceeds limit {limit:.2f} {currency}'
            return self.is_error(), message

        return False, None

    @staticmethod
    def _load_tax_csv(context: dict[str, Any]) -> DataFrame[TaxPaidSchema] | None:
        """Load tax credit CSV from config if available."""
        config = context.get('config', {})
        tax_csv_path = config.get('tax', {}).get('file')
        tax_rate = config.get('tax', {}).get('rate', 0)

        if not tax_csv_path:
            return None

        return load_prepaid_tax_data_from_csv(Path(tax_csv_path), tax_rate)


RULE_TYPES = {
    'balance-limit': BalanceLimitRule,
    'balance-limit-from-attribute': BalanceLimitRule,
    'date-passed-from-attribute': DatePassedRule,
    'price-staleness': PriceStalenessRule,
    'price-limit': PriceLimitRule,
    'price-limit-from-attribute': PriceLimitRule,
    'purchase-cost-limit': PurchaseCostLimitRule,
    'purchase-cost-limit-from-attribute': PurchaseCostLimitRule,
}


def create_rule(rule_config: dict[str, Any]) -> ValidationRule:
    rule_type = rule_config['type']
    if rule_type not in RULE_TYPES:
        raise ValueError(f'Unknown rule type: {rule_type}')

    value = rule_config['value']
    severity = rule_config.get('severity', 'error')
    applies_to = rule_config.get('applies-to', None)

    rule_class = RULE_TYPES[rule_type]
    return rule_class(
        rule_type=rule_type,
        value=value,
        severity=severity,
        applies_to=applies_to
    )  # type: ignore[abstract]


def get_applicable_rules(entity_id: str, entity: pd.Series, rules: list[ValidationRule]) -> list[ValidationRule]:
    applicable_rules: list[ValidationRule] = []

    for rule in rules:
        if rule.matches_entity(entity, entity_id):
            applicable_rules.append(rule)

    return applicable_rules
