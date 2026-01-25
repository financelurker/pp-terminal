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

import logging
from pathlib import Path

from rich.console import Console
import typer

from pp_terminal.data.xml_anonymizer import XmlAnonymizer
from pp_terminal.exceptions import InputError
from pp_terminal.utils.config import get_command_config

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


@app.command(name="anonymized")
def export_anonymized(
    ctx: typer.Context,
    output_file: Path = typer.Option(
        ...,
        help="Output path for anonymized XML file",
        file_okay=True,
        dir_okay=False,
    ),
    seed: int = typer.Option(42, help="Random seed for deterministic anonymization"),
) -> None:
    """
    Create an anonymized copy of Portfolio Performance XML file.

    Anonymizes names, amounts, dates, and notes while preserving:
    - XML structure and references
    - UUIDs
    - Financial identifiers (ISIN, WKN, ticker symbols)
    - Relative timing between transactions
    - Order of magnitude for amounts

    Use the same seed to get reproducible anonymization.
    """

    input_file = ctx.obj.file_path
    output = ctx.obj.output
    config = ctx.obj.config

    if output_file.exists():
        raise InputError(f"Output file {output_file} already exists")

    log.debug("Using seed value %s", seed)

    anonymizer = XmlAnonymizer(seed=seed, config=get_command_config(config, 'export.anonymized.attributes'))

    anonymizer.anonymize_file(input_file, output_file)
    console.print(output.text(f"Anonymized Portfolio Performance file saved to {output_file}"))
