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
import shutil
from pathlib import Path
from typing import cast

from rich.console import Console
import typer

from pp_terminal.exceptions import InputError
from pp_terminal.output.strategy import OutputStrategy

app = typer.Typer()
console = Console()
log = logging.getLogger(__name__)


@app.command(name="export")
def export_file(
    ctx: typer.Context,
    output_file: Path = typer.Option(
        ...,
        help="Output path for XML file",
        file_okay=True,
        dir_okay=False,
    ),
) -> None:
    """
    Export Portfolio Performance XML file.

    When used with --anonymize flag, exports the anonymized version.
    Otherwise exports the original file.
    """

    source_file = cast(Path, ctx.obj.source_file)
    output = cast(OutputStrategy, ctx.obj.output)

    if output_file.exists():
        raise InputError(f"Output file {output_file} already exists")

    shutil.copy(source_file, output_file)
    console.print(output.text(f"Portfolio Performance file saved to {output_file}"))
