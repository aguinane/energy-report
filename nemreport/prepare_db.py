from pathlib import Path

from nemreader import extend_sqlite, output_folder_as_sqlite
from sqlite_utils import Database

DEFAULT_DIR = Path("data/")


def update_nem_database(output_dir: Path = DEFAULT_DIR):
    db_path = output_folder_as_sqlite(
        file_dir=output_dir,
        output_dir=output_dir,
        split_days=True,
        set_interval=5,
        replace=True,
    )
    db = Database(db_path)
    if "readings" not in db.table_names():
        msg = "No data. Copy some NEM12 files into the data folder first"
        raise FileNotFoundError(msg)
    extend_sqlite(db_path)
    return db_path
