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

import pandas as pd

from pp_terminal.validation.rules import (
    BalanceLimitRule,
    PriceLimitRule,
    get_applicable_rules
)


def test_empty_rules_list() -> None:
    """Test that empty rules list returns empty result."""
    entity = pd.Series({'name': 'Test Entity', 'balance': 1000.0})
    entity_id = 'entity-1'

    result = get_applicable_rules(entity_id, entity, [])

    assert not result


def test_universal_rule_matches_all() -> None:
    """Test that rule with no constraints matches all entities."""
    rule = BalanceLimitRule(
        rule_type='balance-limit',
        value=5000.0,
        severity='error',
        applies_to=None
    )

    entity1 = pd.Series({'name': 'Entity 1', 'balance': 1000.0})
    entity2 = pd.Series({'name': 'Entity 2', 'balance': 2000.0})

    result1 = get_applicable_rules('entity-1', entity1, [rule])
    result2 = get_applicable_rules('entity-2', entity2, [rule])

    assert len(result1) == 1
    assert result1[0] == rule
    assert len(result2) == 1
    assert result2[0] == rule


def test_targeted_rule_matching() -> None:
    """Test that rule with applies_to matches only specified entities."""
    rule = BalanceLimitRule(
        rule_type='balance-limit',
        value=5000.0,
        severity='error',
        applies_to=['entity-1', 'entity-3']
    )

    entity1 = pd.Series({'name': 'Entity 1', 'balance': 1000.0})
    entity2 = pd.Series({'name': 'Entity 2', 'balance': 2000.0})
    entity3 = pd.Series({'name': 'Entity 3', 'balance': 3000.0})

    result1 = get_applicable_rules('entity-1', entity1, [rule])
    result2 = get_applicable_rules('entity-2', entity2, [rule])
    result3 = get_applicable_rules('entity-3', entity3, [rule])

    assert len(result1) == 1
    assert result1[0] == rule
    assert len(result2) == 0
    assert len(result3) == 1
    assert result3[0] == rule


def test_from_attribute_rule_matching() -> None:
    """Test that from-attribute rule matches when attribute exists and is not NA."""
    attr_uuid = 'custom-attr-uuid-123'
    rule = BalanceLimitRule(
        rule_type='balance-limit-from-attribute',
        value=attr_uuid,
        severity='error',
        applies_to=None
    )

    entity_with_attr = pd.Series({
        'name': 'Entity With Attr',
        'balance': 1000.0,
        attr_uuid: 8000.0
    })

    entity_without_attr = pd.Series({
        'name': 'Entity Without Attr',
        'balance': 1000.0
    })

    result_with = get_applicable_rules('entity-1', entity_with_attr, [rule])
    result_without = get_applicable_rules('entity-2', entity_without_attr, [rule])

    assert len(result_with) == 1
    assert result_with[0] == rule
    assert len(result_without) == 0


def test_from_attribute_rule_with_na_value() -> None:
    """Test that from-attribute rule does not match when attribute value is NA."""
    attr_uuid = 'custom-attr-uuid-456'
    rule = PriceLimitRule(
        rule_type='price-limit-from-attribute',
        value=attr_uuid,
        severity='error',
        applies_to=None
    )

    entity_with_na = pd.Series({
        'name': 'Entity With NA',
        'price': 100.0,
        attr_uuid: pd.NA
    })

    result = get_applicable_rules('entity-1', entity_with_na, [rule])

    assert len(result) == 0


def test_multiple_rules_mixed_matching() -> None:
    """Test filtering with multiple rules where some match and some don't."""
    universal_rule = BalanceLimitRule(
        rule_type='balance-limit',
        value=5000.0,
        severity='error',
        applies_to=None
    )

    targeted_rule_match = BalanceLimitRule(
        rule_type='balance-limit',
        value=3000.0,
        severity='warning',
        applies_to=['entity-1']
    )

    targeted_rule_no_match = BalanceLimitRule(
        rule_type='balance-limit',
        value=2000.0,
        severity='error',
        applies_to=['entity-2']
    )

    attr_uuid = 'custom-attr-789'
    attr_rule_match = PriceLimitRule(
        rule_type='price-limit-from-attribute',
        value=attr_uuid,
        severity='error',
        applies_to=None
    )

    entity = pd.Series({
        'name': 'Entity 1',
        'balance': 1000.0,
        attr_uuid: 150.0
    })

    rules = [universal_rule, targeted_rule_match, targeted_rule_no_match, attr_rule_match]
    result = get_applicable_rules('entity-1', entity, rules)

    assert len(result) == 3
    assert universal_rule in result
    assert targeted_rule_match in result
    assert attr_rule_match in result
    assert targeted_rule_no_match not in result


def test_all_rules_match() -> None:
    """Test scenario where all rules match the entity."""
    rule1 = BalanceLimitRule(
        rule_type='balance-limit',
        value=5000.0,
        severity='error',
        applies_to=None
    )

    rule2 = BalanceLimitRule(
        rule_type='balance-limit',
        value=3000.0,
        severity='warning',
        applies_to=['entity-1']
    )

    attr_uuid = 'custom-attr-999'
    rule3 = PriceLimitRule(
        rule_type='price-limit-from-attribute',
        value=attr_uuid,
        severity='error',
        applies_to=None
    )

    entity = pd.Series({
        'name': 'Entity 1',
        'balance': 1000.0,
        attr_uuid: 150.0
    })

    rules = [rule1, rule2, rule3]
    result = get_applicable_rules('entity-1', entity, rules)

    assert len(result) == 3
    assert rule1 in result
    assert rule2 in result
    assert rule3 in result


def test_no_rules_match() -> None:
    """Test scenario where no rules match the entity."""
    targeted_rule1 = BalanceLimitRule(
        rule_type='balance-limit',
        value=5000.0,
        severity='error',
        applies_to=['entity-2', 'entity-3']
    )

    targeted_rule2 = BalanceLimitRule(
        rule_type='balance-limit',
        value=3000.0,
        severity='warning',
        applies_to=['entity-4']
    )

    attr_uuid = 'non-existent-attr'
    attr_rule = PriceLimitRule(
        rule_type='price-limit-from-attribute',
        value=attr_uuid,
        severity='error',
        applies_to=None
    )

    entity = pd.Series({
        'name': 'Entity 1',
        'balance': 1000.0
    })

    rules = [targeted_rule1, targeted_rule2, attr_rule]
    result = get_applicable_rules('entity-1', entity, rules)

    assert len(result) == 0


def test_from_attribute_rule_ignores_applies_to() -> None:
    """Test that from-attribute rules check attribute presence, not applies_to."""
    attr_uuid = 'custom-attr-100'
    rule = BalanceLimitRule(
        rule_type='balance-limit-from-attribute',
        value=attr_uuid,
        severity='error',
        applies_to=['entity-2']  # This should be ignored for from-attribute rules
    )

    entity_with_attr = pd.Series({
        'name': 'Entity 1',
        'balance': 1000.0,
        attr_uuid: 8000.0
    })

    result = get_applicable_rules('entity-1', entity_with_attr, [rule])

    # Should match because attribute exists, even though entity-1 is not in applies_to
    assert len(result) == 1
    assert result[0] == rule


def test_preserves_rule_order() -> None:
    """Test that returned rules maintain their original order."""
    rule1 = BalanceLimitRule(
        rule_type='balance-limit',
        value=5000.0,
        severity='error',
        applies_to=None
    )

    rule2 = PriceLimitRule(
        rule_type='price-limit',
        value=100.0,
        severity='warning',
        applies_to=None
    )

    rule3 = BalanceLimitRule(
        rule_type='balance-limit',
        value=3000.0,
        severity='error',
        applies_to=None
    )

    entity = pd.Series({'name': 'Entity 1', 'balance': 1000.0, 'price': 50.0})

    rules = [rule1, rule2, rule3]
    result = get_applicable_rules('entity-1', entity, rules)

    assert len(result) == 3
    assert result[0] == rule1
    assert result[1] == rule2
    assert result[2] == rule3
