import logging
from pathlib import Path

import typer

from .prepare_db import update_nem_database
from .report import build_reports
from .version import __version__

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(message)s"
logging.basicConfig(level="INFO", format=LOG_FORMAT)
app = typer.Typer()
DEFAULT_DIR = Path(".")


def version_callback(value: bool):
    if value:
        typer.echo(f"nemreport version: {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: bool = typer.Option(False, "--version", callback=version_callback),
) -> None:
    """nemreport

    Generate energy report from NEM meter data files
    """
    pass


@app.command()
def update_db() -> None:
    fp = update_nem_database()
    typer.echo(f"Updated {fp}")


@app.command()
def build() -> None:
    fp = build_reports()
    typer.echo(f"Created {fp}")
