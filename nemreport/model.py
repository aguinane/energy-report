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
) -> Generator[Tuple[str, float, float], None, None]:
    sql = "SELECT day, imp, exp "
    sql += "FROM daily_reads WHERE nmi = :nmi"
    for row in db.query(sql, {"nmi": nmi}):
        dt = datetime.strptime(row["day"], "%Y-%m-%d")
        row = (
            dt,
            row["imp"],
            row["exp"],
        )
        yield row


def get_day_profile(nmi: str):
    db.create_view(
        "combined_readings",
        """
    SELECT nmi, t_start, t_end, SUM(CASE WHEN substr(channel,1,1) = 'B' THEN -1 * value ELSE value END) as value
    FROM readings
    GROUP BY nmi, t_start, t_end
    ORDER BY 1, 2
    """,
        replace=True,
    )
    sql = """
    WITH reads AS (
    SELECT
        strftime('%H:%M', cr.t_start) AS time,
        cr.nmi, cr.t_start, cr.t_end, cr.value
    FROM combined_readings cr
    LEFT JOIN (SELECT NMI, MAX(last_interval) as last_interval FROM nmi_summary
    GROUP BY NMI) li ON li.nmi = cr.nmi
    WHERE cr.t_start >= DATETIME(li.last_interval, '-366 days')
    AND cr.nmi = :nmi
    )
    SELECT time, AVG(value)*12 as value
    FROM reads
    GROUP BY time
    """
    rows = list(db.query(sql, {"nmi": nmi}))
    data = {
        "time": [x["time"] for x in rows],
        "Avg kW": [x["value"] for x in rows],
    }
    for season in ["SUMMER", "AUTUMN", "WINTER", "SPRING"]:
        sql = """
        WITH reads AS (
        SELECT
            (CASE WHEN CAST(strftime('%m', cr.t_start) AS INTEGER) < 3 THEN 'SUMMER'
            ELSE (CASE WHEN CAST(strftime('%m', cr.t_start) AS INTEGER) < 6 THEN 'AUTUMN'
            ELSE (CASE WHEN CAST(strftime('%m', cr.t_start) AS INTEGER) < 9 THEN 'WINTER'
            ELSE (CASE WHEN CAST(strftime('%m', cr.t_start) AS INTEGER) < 12 THEN 'SPRING'
            ELSE 'SUMMER' END) END) END) END) season,
            strftime('%H:%M', cr.t_start) AS time,
            cr.nmi, cr.t_start, cr.t_end, cr.value
        FROM combined_readings cr
        LEFT JOIN (SELECT NMI, MAX(last_interval) as last_interval FROM nmi_summary
        GROUP BY NMI) li ON li.nmi = cr.nmi
        WHERE cr.t_start >= DATETIME(li.last_interval, '-366 days')
        AND cr.nmi = :nmi
        )
        SELECT time, AVG(value)*12 as value
        FROM reads
        WHERE season = :season
        GROUP BY time
        """
        rows = list(db.query(sql, {"nmi": nmi, "season": season}))
        data[season] = [x["value"] for x in rows]
    df = pd.DataFrame(data=data)
    return df


def get_day_profiles(nmi: str):
    sql = """
WITH reads AS (
    SELECT
		strftime('%Y-%m-%d', cr.t_start) AS day,
        strftime('%H:%M', cr.t_start) AS time,
        cr.nmi, cr.t_start, cr.t_end, cr.value
    FROM combined_readings cr
    LEFT JOIN (SELECT NMI, MAX(last_interval) as last_interval FROM nmi_summary
    GROUP BY NMI) li ON li.nmi = cr.nmi
    WHERE cr.t_start >= DATETIME(li.last_interval, '-366 days')
    AND cr.nmi = :nmi
    )
    SELECT day, time, AVG(value)*12 as value
    FROM reads
    GROUP BY day, time
    """
    rows = list(db.query(sql, {"nmi": nmi}))
    data = {
        "day": [x["day"] for x in rows],
        "time": [x["time"] for x in rows],
        "Avg kW": [x["value"] for x in rows],
    }
    df = pd.DataFrame(data=data)
    return df
