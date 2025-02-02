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

import locale
from pathlib import Path
from types import SimpleNamespace
import logging
from typing import Optional

from rich import print # pylint: disable=redefined-builtin
from rich.logging import RichHandler
import typer
from typing_extensions import Annotated

from .exceptions import InputError
from .output import create_strategy, OutputFormat
from .plugins import load_command_plugins
from .pp_portfolio_builder import PpPortfolioBuilder
from . import __version__

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")
app.add_typer(typer.Typer(no_args_is_help=True), name="simulate")
app.add_typer(typer.Typer(no_args_is_help=True), name="list")

# init default logging (this is e.g. import for errors during command plugin load
logging.basicConfig(level=logging.WARN, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=False, show_time=False, show_path=False)])
log = logging.getLogger(__name__)

locale.setlocale(locale.LC_ALL, '')

# Load external plugins dynamically
load_command_plugins(app)


def version_callback(value: bool) -> None:
    if value:
        print(f"[bold]pp-terminal[/bold] version: {__version__}")
        raise typer.Exit()


@app.callback(
    invoke_without_command=True,
    epilog="Small insights today, bigger returns tomorrow.",
    help=f"[bold]pp-terminal[/bold] version {__version__} by [link=https://dev-investor.de]dev-investor[/link]\n\nThe Analytic Companion for Portfolio Performance"
)
def main(
        ctx: typer.Context,
        file: Annotated[Path, typer.Option(envvar="PP_TERMINAL_INPUT_FILE", help="Path to the Portfolio Performance XML file", show_default=False, exists=True, file_okay=True, dir_okay=False, readable=True)],
        format: OutputFormat = OutputFormat.TABLE,  # pylint: disable=redefined-builtin
        version: Annotated[  # pylint: disable=unused-argument
            Optional[bool],
            typer.Option("--version", callback=version_callback, is_eager=True),  # declared the option name to avoid --no-version
        ] = None,
        debug: Annotated[Optional[bool], typer.Option('--debug', help='Enable verbose debug logging')] = None,
) -> None:

    if debug:
        logging.basicConfig(force=True, level=logging.DEBUG, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True, show_time=False)])

    try:
        ctx.obj = SimpleNamespace(
            portfolio=PpPortfolioBuilder(cache_file='.cache.sql' if debug else None).construct(file),
            output=create_strategy(format))

    except (RuntimeError, InputError) as e:
        if debug:
            raise e

        log.critical(e)
        raise typer.Abort()


if __name__ == "__main__":
    app()
