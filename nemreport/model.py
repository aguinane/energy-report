from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Generator, Tuple

import pandas as pd
from dateutil.parser import isoparse
from nemreader.output_db import get_nmi_channels, get_nmi_readings
from pydantic import BaseModel
from sqlite_utils import Database

data_dir = Path("data/")
data_dir.mkdir(exist_ok=True)
DB_PATH = data_dir / "nemdata.db"
db = Database(DB_PATH)


class EnergyReading(BaseModel):
    start: datetime
    value: float


def get_date_range(nmi: str) -> Tuple[datetime, datetime]:
    sql = """select MIN(first_interval) start, MAX(last_interval) end
            from nmi_summary where nmi = :nmi
            """
    row = list(db.query(sql, {"nmi": nmi}))[0]
    start = isoparse(row["start"])
    end = isoparse(row["end"])
    return start, end


def get_usage_df(nmi: str) -> pd.DataFrame:
    channels = get_nmi_channels(DB_PATH, nmi)
    imp_values = defaultdict(int)
    exp_values = defaultdict(int)
    for ch in channels:
        feed_in = True if ch in ["B1"] else False
        for read in get_nmi_readings(DB_PATH, nmi, ch):
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


def get_season_data(nmi: str):
    sql = "SELECT *"
    sql += "FROM latest_year_seasons where nmi = :nmi"
    return list(db.query(sql, {"nmi": nmi}))


def get_annual_data(nmi: str):
    sql = "SELECT *"
    sql += "FROM latest_year where nmi = :nmi"
    return list(db.query(sql, {"nmi": nmi}))[0]


def get_day_data(
    nmi: str,
) -> Generator[Tuple[str, float, float, float, float, float, float], None, None]:
    sql = "SELECT day, imp, exp, imp_morning, imp_day, imp_evening, imp_night "
    sql += "FROM daily_reads where nmi = :nmi"
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
