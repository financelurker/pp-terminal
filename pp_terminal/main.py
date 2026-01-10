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

from .config import load_config
from .exceptions import InputError, ValidationError
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

locale.setlocale(category=locale.LC_ALL, locale='')

# Load external plugins dynamically
load_command_plugins(app)

_DB_FILE = '.cache.db'


def version_callback(value: bool) -> None:
    if value:
        print(f"[bold]pp-terminal[/bold] version: {__version__}")
        raise typer.Exit()


@app.callback(
    invoke_without_command=True,
    epilog="Small insights today, bigger returns tomorrow.",
    help=f"[bold]pp-terminal[/bold] version {__version__} by [link=https://dev-investor.de]dev-investor[/link]\n\nThe Analytic Companion for Portfolio Performance"
)
def main(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        ctx: typer.Context,
        file: Annotated[Optional[Path], typer.Option(help="Path to the Portfolio Performance XML file", show_default=False, exists=True, file_okay=True, dir_okay=False, readable=True)] = None,
        format: Optional[OutputFormat] = None,  # pylint: disable=redefined-builtin
        config: Annotated[Optional[Path], typer.Option(help="Path to config file", show_default=False, exists=True, file_okay=True, dir_okay=False, readable=True)] = None,
        version: Annotated[  # pylint: disable=unused-argument
            Optional[bool],
            typer.Option("--version", callback=version_callback, is_eager=True),  # declared the option name to avoid --no-version
        ] = None,
        debug: Annotated[Optional[bool], typer.Option('--debug', help='Enable verbose debug logging')] = None,
) -> None:

    if debug:
        logging.basicConfig(force=True, level=logging.DEBUG, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True, show_time=False)])

    try:
        config_data = load_config(config)

        final_file = file if file is not None else (Path(config_data['file']) if 'file' in config_data else None)
        if final_file is None:
            raise InputError("Portfolio Performance XML file must be provided via --file option or config file")

        final_format = format if format is not None else OutputFormat(config_data.get('format', 'table'))

        ctx.obj = SimpleNamespace(
            portfolio=PpPortfolioBuilder(cache_file=_DB_FILE if debug else None).construct(final_file),
            output=create_strategy(final_format))

    except (RuntimeError, InputError, ValidationError) as e:
        if debug:
            raise e

        log.critical(e)
        raise typer.Abort()


if __name__ == "__main__":
    app()
