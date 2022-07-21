import logging
from pathlib import Path
from nemreader import output_as_sqlite
import logging
from datetime import datetime
from collections import defaultdict
from statistics import mean
from model import db
from model import get_nmis, get_channels, get_readings
from model import time_of_day, get_season


def import_nem_data():
    output_dir = Path("data/")
    for fp in output_dir.glob("*.csv"):
        print("Importing", fp)
        try:
            output_as_sqlite(
                file_name=fp, output_dir="data/", split_days=True, set_interval=5
            )
        except:
            print("Failed to process", fp)


def calc_daily_summary(nmi: str):
    channels = get_channels(nmi)

    imp_values = defaultdict(lambda: defaultdict(int))
    exp_values = defaultdict(int)
    for ch in channels:
        feed_in = True if ch in ["B1"] else False
        for read in get_readings(nmi, ch):
            day = read.start.strftime("%Y-%m-%d")
            if feed_in:
                exp_values[day] += read.value
            else:
                tod = time_of_day(read.start)
                imp_values[day][tod] += read.value

    for day in imp_values.keys():
        imp1 = round(imp_values[day]["Morning"], 3)
        imp2 = round(imp_values[day]["Day"], 3)
        imp3 = round(imp_values[day]["Evening"], 3)
        imp4 = round(imp_values[day]["Night"], 3)
        imp = imp1 + imp2 + imp3 + imp4
        exp = round(exp_values[day], 3)
        item = {
            "nmi": nmi,
            "day": day,
            "imp": imp,
            "exp": exp,
            "imp_morning": imp1,
            "imp_day": imp2,
            "imp_evening": imp3,
            "imp_night": imp4,
        }
        yield item


def update_daily_summaries():
    """Write daily summary back to database"""
    nmis = get_nmis()
    for nmi in nmis:
        items = calc_daily_summary(nmi)
        db["daily_reads"].upsert_all(
            items, pk=("nmi", "day"), column_order=("nmi", "day")
        )
    logging.info("Updated day data")


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
    nmis = get_nmis()
    for nmi in nmis:
        items = calc_seasonal_summary(nmi)
        db["season_reads"].upsert_all(
            items, pk=("nmi", "year", "season"), column_order=("nmi", "year", "season")
        )
    logging.info("Updated seasonal data")


logging.basicConfig(level="INFO")

# import_nem_data()
update_daily_summaries()
update_seasonal_summaries()
