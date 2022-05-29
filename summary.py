import logging
from datetime import datetime, date
from collections import defaultdict
from typing import List
from pydantic import BaseModel
from sqlite_utils import Database
from statistics import mean
import pandas as pd

db = Database("nemdata.db")


class EnergyReading(BaseModel):
    start: datetime
    value: float


def time_of_day(start: datetime) -> str:
    """Get time of day period"""
    s = start
    if s.hour < 4:
        return "Night"
    if s.hour < 9:
        return "Morning"
    if s.hour < 16:
        return "Day"
    if s.hour < 21:
        return "Evening"
    return "Night"


def get_nmis() -> List[str]:
    nmis = []
    for row in db.query("select distinct nmi from nmi_summary"):
        nmis.append(row["nmi"])
    return nmis


def get_readings(nmi: str, channel: str) -> List[EnergyReading]:
    reads = []
    for r in db.query(
        "select * from readings where nmi = :nmi and channel = :ch",
        {"nmi": nmi, "ch": channel},
    ):
        read = EnergyReading(start=r["t_start"], value=r["value"])
        reads.append(read)
    return reads


def calc_daily_summary(nmi: str):
    channels = []
    for row in db.query("select * from nmi_summary where nmi = :nmi", {"nmi": nmi}):
        channels.append(row["channel"])

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


def get_fiscal_year(day: date) -> int:
    """Get FY ending"""
    if day.month <= 6:
        fy = day.year
    else:
        fy = day.year + 1
    return fy


def get_season(day: date) -> str:
    """Get season for day"""
    if day.month in [1, 2, 12]:
        return "A - Summer"
    if day.month in [3, 4, 5]:
        return "B - Autumn"
    if day.month in [6, 7, 8]:
        return "C - Winter"
    return "D - Spring"


def get_season_fy(day: date) -> str:
    season = get_season(day)
    if day.month == 12:
        fyd = str(day.year + 1)
    else:
        fyd = str(day.year)
    return f"{fyd} {season}"


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


def get_usage_df(nmi: str):
    channels = []
    for row in db.query("select * from nmi_summary where nmi = :nmi", {"nmi": nmi}):
        channels.append(row["channel"])

    channels = []
    for row in db.query("select * from nmi_summary where nmi = :nmi", {"nmi": nmi}):
        channels.append(row["channel"])

    imp_values = defaultdict(int)
    exp_values = defaultdict(int)
    for ch in channels:
        feed_in = True if ch in ["B1"] else False
        for read in get_readings(nmi, ch):
            dt = read.start
            if feed_in:
                exp_values[dt] += read.value
            else:
                imp_values[dt] += read.value

    df = pd.DataFrame(
        data={"consumption": [imp_values[x] for x in imp_values]}, index=imp_values.keys()
    )
    ser = pd.Series(data=[-exp_values[x] for x in exp_values], index=exp_values.keys())
    df.loc[:, "export"] = ser
    return df.fillna(0)
