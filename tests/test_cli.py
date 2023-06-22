import pytest
from typer.testing import CliRunner

from nemreport.cli import app


@pytest.fixture
def runner():
    return CliRunner()


def test_cli_version(runner):
    result = runner.invoke(app, ["--version"])
    assert "nemreport version:" in result.stdout
    assert result.exit_code == 0


def test_cli_db_update(runner):
    result = runner.invoke(app, ["update-db"])
    assert "nemdata.db" in result.stdout
    assert result.exit_code == 0


def test_cli_build(runner):
    result = runner.invoke(app, ["build"])

    assert result.exit_code == 0
