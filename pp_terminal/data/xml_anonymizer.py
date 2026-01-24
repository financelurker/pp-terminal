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

from pathlib import Path
import random
from datetime import datetime, timedelta

import lxml.etree as ET  # pylint: disable=c-extension-no-member
from faker import Faker


class XmlAnonymizer:
    """Anonymizes Portfolio Performance XML files."""

    # Tags that should not be anonymized
    SKIP_TAGS = {
        'uuid', 'isin', 'wkn', 'tickerSymbol', 'feed', 'feedURL',
        'currencyCode', 'targetCurrencyCode', 'calendar', 'type',
        'isRetired', 'updatedAt', 'version', 'baseCurrency'
    }

    def __init__(
        self,
        seed: int,
        date_shift_days_range: tuple[int, int] = (-3650, -365),
        amount_factor_range: tuple[float, float] = (0.5, 2.0)
    ):
        self.seed = seed
        self.date_shift_days_range = date_shift_days_range
        self.amount_factor_range = amount_factor_range

        self.rng = random.Random(seed)
        self.faker = Faker()
        Faker.seed(seed)

        # Caches for consistent anonymization
        self.amount_factors: dict[str, float] = {}
        self.date_offset: int | None = None

    def anonymize_file(self, input_path: Path, output_path: Path) -> None:
        """Anonymize XML file."""
        # Parse XML preserving formatting
        parser = ET.XMLParser(remove_blank_text=False)
        tree = ET.parse(str(input_path), parser)
        root = tree.getroot()

        self._init_date_offset()
        self._anonymize_element(root)

        # Write output preserving original formatting
        tree.write(
            str(output_path),
            encoding='UTF-8',
            xml_declaration=True,
            pretty_print=False
        )

    def _init_date_offset(self) -> None:
        """Initialize random date offset."""
        min_days, max_days = self.date_shift_days_range
        self.date_offset = self.rng.randint(min_days, max_days)

    def _anonymize_element(self, element: ET.Element) -> None:
        """Recursively anonymize XML element and children."""
        tag = element.tag

        if tag in self.SKIP_TAGS:
            # Still process children
            for child in element:
                self._anonymize_element(child)
            return

        if tag == 'name':
            element.text = self._generate_name(element)
        elif tag == 'note':
            element.text = self.faker.sentence() if element.text else None
        elif tag == 'date':
            element.text = self._shift_date(element.text)
        elif tag == 'amount':
            element.text = self._randomize_amount(element.text, element)
            # Also handle amount attribute for multi-currency amounts
            if 'amount' in element.attrib:
                element.attrib['amount'] = self._randomize_amount(
                    element.attrib['amount'], element
                )
        elif tag == 'shares':
            element.text = self._randomize_amount(element.text, element)
        elif tag == 'price':
            # Price element has 't' (date) and 'v' (value) attributes
            if 't' in element.attrib:
                element.attrib['t'] = self._shift_date(element.attrib['t'])
            if 'v' in element.attrib:
                element.attrib['v'] = self._randomize_amount(
                    element.attrib['v'], element
                )
        elif tag == 'source':
            element.text = self.faker.file_name(extension="pdf") if element.text else None

        for child in element:
            self._anonymize_element(child)

    def _generate_name(self, element: ET.Element) -> str:  # pylint: disable=too-many-return-statements
        """Generate fake name based on parent context."""
        # Get current text for fallback
        current_text = element.text

        if not current_text or not current_text.strip():
            return str(current_text)

        parent = element.getparent()
        if parent is None:
            return self.faker.company()

        parent_tag = parent.tag
        if parent_tag in ('security', 'attribute-type'):
            return str(element.text)
        if 'account' in parent_tag.lower():
            return f"{self.faker.word().capitalize()} Account"
        if 'portfolio' in parent_tag.lower():
            return f"{self.faker.word().capitalize()} Portfolio"

        return self.faker.catch_phrase()

    def _shift_date(self, date_str: str | None) -> str:
        """Shift date by random offset."""
        if not date_str or not self.date_offset:
            return str(date_str)

        try:
            if 'T' in date_str:
                # ISO format with time: "2019-01-01T00:00"
                # Handle optional Z suffix
                clean_date = date_str.replace('Z', '+00:00')
                dt = datetime.fromisoformat(clean_date)
                shifted = dt + timedelta(days=self.date_offset)
                # Preserve original format
                if date_str.endswith('Z'):
                    return shifted.isoformat().replace('+00:00', 'Z')
                return shifted.isoformat()

            # Date only: "2019-01-01"
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            shifted = dt + timedelta(days=self.date_offset)
            return shifted.strftime('%Y-%m-%d')
        except (ValueError, AttributeError):
            return date_str

    def _randomize_amount(self, amount_str: str | None, element: ET.Element) -> str:
        """Randomize amount while preserving order of magnitude."""
        if not amount_str:
            return str(amount_str)

        try:
            # Build context key for consistency
            parent = element.getparent()
            context = f"{element.tag}_{parent.tag if parent is not None else ''}"

            # Get or generate factor
            if context not in self.amount_factors:
                min_f, max_f = self.amount_factor_range
                self.amount_factors[context] = self.rng.uniform(min_f, max_f)

            factor = self.amount_factors[context]
            value = int(amount_str)
            new_value = int(value * factor)

            return str(new_value)
        except (ValueError, AttributeError):
            return amount_str
