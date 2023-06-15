from pathlib import Path

from nemreader import extend_sqlite, output_folder_as_sqlite


def update_nem_database():
    output_dir = Path("data/")

    db_path = output_folder_as_sqlite(
        file_dir=output_dir,
        output_dir=output_dir,
        split_days=True,
        set_interval=5,
        replace=True,
    )
    extend_sqlite(db_path)
