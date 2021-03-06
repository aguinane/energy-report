from datetime import datetime, date
from collections import defaultdict
from typing import List, Generator, Tuple
from pydantic import BaseModel
from sqlite_utils import Database
import pandas as pd
from dateutil.parser import isoparse

db = Database("data/nemdata.db")


class EnergyReading(BaseModel):
    start: datetime
    value: float


def get_nmis() -> List[str]:
    nmis = []
    for row in db.query("select distinct nmi from nmi_summary"):
        nmis.append(row["nmi"])
    return nmis


def get_channels(nmi: str) -> List[str]:
    channels = []
    for row in db.query("select * from nmi_summary where nmi = :nmi", {"nmi": nmi}):
        channels.append(row["channel"])
    return channels


def get_readings(nmi: str, channel: str) -> List[EnergyReading]:
    reads = []
    for r in db.query(
        "select * from readings where nmi = :nmi and channel = :ch",
        {"nmi": nmi, "ch": channel},
    ):
        read = EnergyReading(start=r["t_start"], value=r["value"])
        reads.append(read)
    return reads


def get_date_range(nmi: str) -> Tuple[datetime, datetime]:
    sql = """select MIN(first_interval) start, MAX(last_interval) end 
            from nmi_summary where nmi = :nmi
            """
    row = list(db.query(sql, {"nmi": nmi}))[0]
    start = isoparse(row["start"])
    end = isoparse(row["end"])
    return start, end


def get_years(nmi: str) -> Generator[int, None, None]:
    start, end = get_date_range(nmi)
    x = start.year
    while x <= end.year:
        yield x
        x += 1


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


def get_usage_df(nmi: str) -> pd.DataFrame:

    channels = get_channels(nmi)
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
        data={"consumption": [imp_values[x] for x in imp_values]},
        index=imp_values.keys(),
    )
    ser = pd.Series(data=[-exp_values[x] for x in exp_values], index=exp_values.keys())
    df.loc[:, "export"] = ser
    return df.fillna(0)


def get_day_data(
    nmi: str,
) -> Generator[Tuple[str, float, float, float, float, float, float], None, None]:
    sql = "select day, imp, exp, imp_morning, imp_day, imp_evening, imp_night from daily_reads where nmi = :nmi"
    for row in db.query(sql, {"nmi": nmi}):
        dt = datetime.strptime(row["day"], "%Y-%m-%d")
        row = (
            dt,
            row["imp"],
            row["exp"],
            row["imp_morning"],
            row["imp_day"],
            row["imp_evening"],
            row["imp_night"],
        )
        yield row
