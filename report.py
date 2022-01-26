import logging
from datetime import datetime
from typing import Optional
import shutil
from dateutil.parser import isoparse
from pathlib import Path
import pandas as pd
from collections import defaultdict
import calplot
from sqlite_utils import Database
from summary import update_daily_summaries
from summary import update_seasonal_summaries
from summary import get_nmis
from jinja2 import Environment, FileSystemLoader

db = Database("nemdata.db")


def format_month(dt: datetime) -> str:
    return dt.strftime("%b %Y")


def get_date_range(nmi: str):
    sql = """select MIN(first_interval) start, MAX(last_interval) end 
            from nmi_summary where nmi = :nmi
            """
    row = list(db.query(sql, {"nmi": nmi}))[0]
    start = isoparse(row["start"])
    end = isoparse(row["end"])
    return start, end

def get_years(nmi: str):
    start, end = get_date_range(nmi)
    x = start.year
    while x <= end.year:
        yield x
        x += 1

def get_day_data(nmi: str):
    sql = "select day, imp, exp from daily_reads where nmi = :nmi"
    for row in db.query(sql, {"nmi": nmi}):
        dt = datetime.strptime(row["day"], "%Y-%m-%d")
        row = dt, row["imp"], row["exp"]
        yield row


def get_import_overview_chart(nmi: str) -> Path:
    """Save calendar plot"""
    days = []
    data = []
    for dt, imp, _ in get_day_data(nmi):
        days.append(dt)
        data.append(imp)

    data = pd.Series(data, index=days)
    plot = calplot.calplot(
        data,
        suptitle=f"Daily kWh for {nmi}",
        how=None,
        vmin=0,
        vmax=35,
        cmap="YlOrRd",
        daylabels="MTWTFSS",
        colorbar=True,
    )
    fig = plot[0]
    file_path = Path(f"build/{nmi}_import.png")
    fig.savefig(file_path, bbox_inches="tight")
    logging.info("Created %s", file_path)
    return file_path


def get_export_overview_chart(nmi: str) -> Optional[Path]:
    """Save calendar plot"""
    days = []
    data = []
    for dt, _, exp in get_day_data(nmi):
        if exp:
            days.append(dt)
            data.append(exp)

    if len(data) == 0:
        return None
    data = pd.Series(data, index=days)
    plot = calplot.calplot(
        data,
        suptitle=f"Daily Export kWh for {nmi}",
        how=None,
        vmin=0,
        vmax=35,
        cmap="Greens",
        daylabels="MTWTFSS",
        colorbar=True,
    )
    fig = plot[0]
    file_path = Path(f"build/{nmi}_export.png")
    fig.savefig(file_path, bbox_inches="tight")
    logging.info("Created %s", file_path)
    return file_path

def copy_static_data():
    """Copy static file"""
    files = ["bootstrap.min.css"]
    for file in files:
        shutil.copy(f"templates/{file}", f"build/{file}")


def get_seasonal_data(nmi: str):
    year_data = {}
    for year in get_years(nmi):
        data = get_year_season_data(nmi, year)
        year_data[year] = data
    return year_data

def get_year_season_data(nmi: str, year: int):
    imp_values = {}
    exp_values = {}

    sql = """select season, imp, exp 
            from season_reads
            where nmi = :nmi and year = :year
            """
    for r in db.query(sql, {"nmi": nmi, "year": year}):
        season = r["season"]
        imp = r["imp"]
        exp = r["exp"]
        imp_values[season] = imp
        exp_values[season] = exp

    a_days = 90
    a_avg = imp_values.get("A - Summer", None)
    a_sum = a_avg * a_days if a_avg else None

    b_days = 92
    b_avg = imp_values.get("B - Autumn", None)
    b_sum = b_avg * b_days if b_avg else None

    c_days = 92
    c_avg = imp_values.get("C - Winter", None)
    c_sum = c_avg * c_days if c_avg else None

    d_days = 91
    d_avg = imp_values.get("D - Spring", None)
    d_sum = d_avg * d_days if d_avg else None

    yr_sum = 0
    yr_days = 0
    if a_sum is not None:
        yr_sum += a_sum
        yr_days += a_days
    if b_sum is not None:
        yr_sum += b_sum
        yr_days += b_days
    if c_sum is not None:
        yr_sum += c_sum
        yr_days += c_days
    if d_sum is not None:
        yr_sum += d_sum
        yr_days += d_days
    yr_avg = round(yr_sum / yr_days,3)

    summary = {
        "Summer": (a_avg, a_sum),
        "Autumn": (b_avg, b_sum),
        "Winter": (c_avg, c_sum),
        "Spring": (d_avg, d_sum),
        "Year": (yr_avg, yr_sum),
    }
    return summary


def build_report(nmi: str):
    template = env.get_template("nmi-report.html")
    start, end = get_date_range(nmi)
    fp_imp = get_import_overview_chart(nmi)
    fp_exp = get_export_overview_chart(nmi)
    has_export = True if fp_exp else None
    report_data = {
        "start": start,
        "end": end,
        "has_export": has_export,
        "imp_overview_chart": fp_imp.name,
        "exp_overview_chart": fp_exp.name if has_export else None,
        "season_data": get_seasonal_data(nmi),
    }
    print(report_data)
    output_html = template.render(nmi=nmi, **report_data)
    file_path = f"build/{nmi}.html"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(output_html)
    logging.info("Created %s", file_path)


logging.basicConfig(level="INFO")
Path("build").mkdir(exist_ok=True)

# update_daily_summaries()
# update_seasonal_summaries()


env = Environment(loader=FileSystemLoader("templates"))
env.filters["yearmonth"] = format_month

# copy_static_data()
for nmi in get_nmis():

    build_report(nmi)
