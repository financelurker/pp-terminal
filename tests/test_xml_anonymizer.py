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

import lxml.etree as ET  # pylint: disable=c-extension-no-member

from pp_terminal.data.xml_anonymizer import XmlAnonymizer


def test_date_shifting_preserves_order():
    """Relative date order is preserved after anonymization."""
    anon = XmlAnonymizer(seed=42)
    anon._init_date_offset()  # pylint: disable=protected-access

    date1 = "2019-01-01"
    date2 = "2019-06-01"

    shifted1 = anon._shift_date(date1)  # pylint: disable=protected-access
    shifted2 = anon._shift_date(date2)  # pylint: disable=protected-access

    assert shifted1 < shifted2, "Date order should be preserved"


def test_date_shifting_with_time():
    """Date shifting works with ISO datetime format."""
    anon = XmlAnonymizer(seed=42)
    anon._init_date_offset()  # pylint: disable=protected-access

    date_with_time = "2019-01-01T00:00"
    shifted = anon._shift_date(date_with_time)  # pylint: disable=protected-access

    assert "T" in shifted, "Time component should be preserved"
    assert shifted != date_with_time, "Date should be changed"


def test_xstream_ids_unchanged(tmp_path):
    """XStream id and reference attributes are not modified."""
    # Create test XML with id and reference
    xml_content = """<client id="1">
  <account id="20">
    <name>Test Account</name>
  </account>
  <portfolio id="24">
    <name>Test Portfolio</name>
    <referenceAccount reference="20"/>
  </portfolio>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    # Anonymize
    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    # Parse output and check ids/references
    tree = ET.parse(str(output_file))
    root = tree.getroot()

    assert root.get('id') == '1', "Root id should be unchanged"
    account = root.find('.//account')
    assert account.get('id') == '20', "Account id should be unchanged"
    ref_account = root.find('.//referenceAccount')
    assert ref_account.get('reference') == '20', "Reference should be unchanged"


def test_uuids_unchanged(tmp_path):
    """UUID elements are kept as-is."""
    xml_content = """<client id="1">
  <security id="2">
    <uuid>f52d3250-9a9f-4fd5-b4e4-5bcf705e0a15</uuid>
    <name>Test Security</name>
  </security>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    uuid_elem = tree.find('.//uuid')
    assert uuid_elem.text == "f52d3250-9a9f-4fd5-b4e4-5bcf705e0a15", "UUID should be unchanged"


def test_financial_ids_preserved(tmp_path):
    """ISIN, WKN, tickerSymbol remain unchanged."""
    xml_content = """<client id="1">
  <security id="2">
    <name>Test Security</name>
    <isin>DE0008469008</isin>
    <wkn>846900</wkn>
    <tickerSymbol>^GDAXI</tickerSymbol>
  </security>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    security = tree.find('.//security')

    assert security.find('isin').text == "DE0008469008", "ISIN should be unchanged"
    assert security.find('wkn').text == "846900", "WKN should be unchanged"
    assert security.find('tickerSymbol').text == "^GDAXI", "Ticker should be unchanged"


def test_amount_randomization_preserves_magnitude(tmp_path):
    """Amount randomization keeps values in reasonable range."""
    xml_content = """<client id="1">
  <account id="2">
    <name>Test</name>
    <transactions>
      <account-transaction>
        <amount>1000000</amount>
      </account-transaction>
    </transactions>
  </account>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42, amount_factor_range=(0.5, 2.0))
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    amount = tree.find('.//amount')
    new_amount = int(amount.text)

    assert 500000 <= new_amount <= 2000000, f"Amount {new_amount} out of expected range"
    assert new_amount != 1000000, "Amount should be changed"


def test_names_are_anonymized(tmp_path):
    """Names are replaced with fake names."""
    xml_content = """<client id="1">
  <security id="2">
    <name>Real Company Name</name>
  </security>
  <account id="3">
    <name>My Personal Account</name>
  </account>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    security_name = tree.find('.//security/name').text
    account_name = tree.find('.//account/name').text

    assert security_name == "Real Company Name", "Security name should NOT be changed"
    assert account_name != "My Personal Account", "Account name should be changed"


def test_notes_are_anonymized(tmp_path):
    """Notes are replaced with placeholder."""
    xml_content = """<client id="1">
  <account id="2">
    <name>Test</name>
    <note>This is my personal note with sensitive info</note>
  </account>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    note = tree.find('.//note').text

    assert note != "This is my personal note with sensitive info", "Note should be replaced"


def test_empty_notes_preserved(tmp_path):
    """Empty notes remain empty."""
    xml_content = """<client id="1">
  <account id="2">
    <name>Test</name>
    <note></note>
  </account>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    note = tree.find('.//note')

    # Empty note should remain empty or None
    assert not note.text or not note.text.strip(), "Empty note should remain empty"


def test_deterministic_anonymization(tmp_path):
    """Same seed produces same output."""
    xml_content = """<client id="1">
  <security id="2">
    <name>Test Security</name>
  </security>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file1 = tmp_path / "output1.xml"
    output_file2 = tmp_path / "output2.xml"
    input_file.write_text(xml_content)

    # Anonymize twice with same seed
    anonymizer1 = XmlAnonymizer(seed=42)
    anonymizer1.anonymize_file(input_file, output_file1)

    anonymizer2 = XmlAnonymizer(seed=42)
    anonymizer2.anonymize_file(input_file, output_file2)

    content1 = output_file1.read_text()
    content2 = output_file2.read_text()

    assert content1 == content2, "Same seed should produce same output"


def test_price_attributes_anonymized(tmp_path):
    """Price element attributes (date and value) are anonymized."""
    xml_content = """<client id="1">
  <security id="2">
    <name>Test</name>
    <prices>
      <price t="2015-01-16" v="1016776950000"/>
    </prices>
  </security>
</client>"""

    input_file = tmp_path / "test_input.xml"
    output_file = tmp_path / "test_output.xml"
    input_file.write_text(xml_content)

    anonymizer = XmlAnonymizer(seed=42)
    anonymizer.anonymize_file(input_file, output_file)

    tree = ET.parse(str(output_file))
    price = tree.find('.//price')

    assert price.get('t') != "2015-01-16", "Price date should be changed"
    assert price.get('v') != "1016776950000", "Price value should be changed"
