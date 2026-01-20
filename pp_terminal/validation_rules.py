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
from typing import Any
import logging
import pandas as pd

log = logging.getLogger(__name__)


class ValidationRule(ABC):
    def __init__(self, rule_config: dict[str, Any]):
        self.rule_type = str(rule_config['type'])
        self._value = rule_config['value']
        self.severity = rule_config.get('severity', 'error')
        self.applies_to = rule_config.get('applies-to', None)

    @abstractmethod
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        """
        Validate entity and return (is_error, message) tuple.

        Returns:
            tuple[bool, str | None]:
                - First element: True if error occurred (severity='error' and validation failed)
                - Second element: Violation message if validation failed, None otherwise
        """
        log.debug('Validating %s of "%s" (%s) using value %s %s', str(self), entity["Name"], entity_id, str(self._get_value(entity)), '(' + str(self._value) + ')' if self._value != self._get_value(entity) else '')

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
            message = f'Account "{entity["Name"]}" ({entity_id}) balance {balance:.2f} exceeds limit {limit:.2f}'
            self.log_violation(message)
            return (self.is_error(), message)
        return (False, None)


class DatePassedRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        date_value = self._get_value(entity)

        if pd.isna(date_value):
            return (False, None)

        if not isinstance(date_value, datetime):
            try:
                date_value = pd.to_datetime(date_value)
            except (ValueError, TypeError):
                log.warning('Account "%s" has invalid date value: %s', entity["Name"], date_value)
                return (False, None)

        current_date = datetime.now()
        if date_value < current_date:
            message = f'Account "{entity["Name"]}" date attribute has passed {date_value.strftime("%Y-%m-%d")}'
            self.log_violation(message)
            return (self.is_error(), message)
        return (False, None)


class PriceStalenessRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        max_days = self._get_value(entity)
        latest_price_date = context.get('latest_price_date')

        if pd.isna(latest_price_date) or latest_price_date is None:
            message = f'Security "{entity["Name"]}" has no price data'
            self.log_violation(message)
            return (self.is_error(), message)

        current_date = datetime.now()
        days_old = (current_date - latest_price_date).days

        if days_old > max_days:
            message = f'Security "{entity["Name"]}" price is {days_old} days old (latest price from {latest_price_date.strftime("%Y-%m-%d")})'
            self.log_violation(message)
            return (self.is_error(), message)
        return (False, None)


class PriceLimitRule(ValidationRule):
    def validate(self, entity: pd.Series, entity_id: str, context: dict[str, Any]) -> tuple[bool, str | None]:
        super().validate(entity, entity_id, context)

        limit = self._get_value(entity)
        current_price = context.get('current_price')

        if pd.isna(current_price):
            message = f'Security "{entity["Name"]}" has no price data'
            self.log_violation(message)
            return (self.is_error(), message)

        if current_price >= limit:
            message = f'Security "{entity["Name"]}" price {current_price:.2f} has reached limit {limit:.2f}'
            self.log_violation(message)
            return (self.is_error(), message)
        return (False, None)


RULE_TYPES = {
    'balance-limit': BalanceLimitRule,
    'balance-limit-from-attribute': BalanceLimitRule,
    'date-passed-from-attribute': DatePassedRule,
    'price-staleness': PriceStalenessRule,
    'price-limit': PriceLimitRule,
    'price-limit-from-attribute': PriceLimitRule,
}


def create_rule(rule_config: dict[str, Any], config: dict[str, Any] | None = None) -> ValidationRule:
    rule_type = rule_config['type']
    if rule_type not in RULE_TYPES:
        raise ValueError(f'Unknown rule type: {rule_type}')

    # Resolve attribute names to UUIDs for *-from-attribute rules
    if rule_type.endswith('-from-attribute'):
        if config is None:
            raise ValueError(f'Config required for rule type: {rule_type}')

        attr_name = rule_config['value']
        attributes = config.get('attributes', {})

        if attr_name not in attributes:
            raise ValueError(f'Attribute "{attr_name}" not found in config.attributes')

        # Replace friendly name with UUID in the rule config
        resolved_config = rule_config.copy()
        resolved_config['value'] = attributes[attr_name]
        rule_class = RULE_TYPES[rule_type]
        return rule_class(resolved_config)  # type: ignore[abstract]

    rule_class = RULE_TYPES[rule_type]
    return rule_class(rule_config)  # type: ignore[abstract]


def get_applicable_rules(entity_id: str, entity: pd.Series, rules: list[ValidationRule]) -> list[ValidationRule]:
    """Get all applicable rules, but only the first match per rule class."""
    applicable_rules: list[ValidationRule] = []
    seen_classes: set[type] = set()

    for rule in rules:
        if rule.matches_entity(entity, entity_id):
            rule_class = type(rule)
            if rule_class not in seen_classes:
                applicable_rules.append(rule)
                seen_classes.add(rule_class)

    return applicable_rules
