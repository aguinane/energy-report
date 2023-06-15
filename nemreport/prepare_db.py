import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from nemreader import extend_sqlite, output_as_sqlite
from nemreader.output_db import get_nmis

from .model import DB_PATH, db, get_season


def calc_seasonal_summary(nmi: str):
    """Get seasonal summaries"""

    imp_values = defaultdict(lambda: defaultdict(list))
    exp_values = defaultdict(list)

    for row in db.query("select * from daily_reads where nmi = :nmi", {"nmi": nmi}):
        day = datetime.strptime(row["day"], "%Y-%m-%d").date()

        season = get_season(day)
        year = day.year + 1 if day.month == 12 else day.year
        key = (year, season)
        imp_values[key]["total"].append(row["imp"])
        imp_values[key]["morning"].append(row["imp_morning"])
        imp_values[key]["day"].append(row["imp_day"])
        imp_values[key]["evening"].append(row["imp_evening"])
        imp_values[key]["night"].append(row["imp_night"])
        exp_values[key].append(row["exp"])

    for key in imp_values.keys():
        imp = mean(imp_values[key]["total"])
        imp1 = mean(imp_values[key]["morning"])
        imp2 = mean(imp_values[key]["day"])
        imp3 = mean(imp_values[key]["evening"])
        imp4 = mean(imp_values[key]["night"])
        exp = mean(exp_values[key])
        year, season = key
        item = {
            "nmi": nmi,
            "year": year,
            "season": season,
            "imp": round(imp, 3),
            "exp": round(exp, 3),
            "imp_morning": round(imp1, 3),
            "imp_day": round(imp2, 3),
            "imp_evening": round(imp3, 3),
            "imp_night": round(imp4, 3),
        }
        yield item


def update_seasonal_summaries():
    """Write seasonal summary back to database"""
    nmis = get_nmis(DB_PATH)
    for nmi in nmis:
        items = calc_seasonal_summary(nmi)
        db["season_reads"].upsert_all(
            items, pk=("nmi", "year", "season"), column_order=("nmi", "year", "season")
        )
    logging.info("Updated seasonal data")


def update_nem_database():
    output_dir = Path("data/")
    for fp in output_dir.glob("*.csv"):
        print("Importing", fp)
        try:
            output_as_sqlite(
                file_name=fp, output_dir="data/", split_days=True, set_interval=5
            )
        except Exception:
            print("Failed to process", fp)

    extend_sqlite(DB_PATH)
    update_seasonal_summaries()
