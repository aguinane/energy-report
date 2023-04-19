import logging
import shutil
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import calplot
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from sqlite_utils import Database

from nemreader.output_db import get_nmis
from model import get_date_range, get_day_data, get_usage_df, get_years

DB_PATH = Path("data/") / "nemdata.db"
db = Database(DB_PATH)
log = logging.getLogger(__name__)


def format_month(dt: datetime) -> str:
    return dt.strftime("%b %Y")


def build_daily_usage_chart(nmi: str, kind: str) -> Optional[Path]:
    """Save calendar plot"""
    days = []
    data = []
    for dt, imp, exp, _, _, _, _ in get_day_data(nmi):
        days.append(dt)
        exp = -exp  # Make export negative
        if kind == "import":
            data.append(imp)
        elif kind == "export":
            data.append(exp)
        elif kind == "total":
            val = imp + exp
            data.append(val)
        else:
            raise ValueError("Invalid usage chart kind")

    if kind == "export":
        if min(data) == 0.0:
            return None

    vmin = max(-35, min(data))
    vmax = min(35, max(data))

    data = pd.Series(data, index=days)
    plot = calplot.calplot(
        data,
        suptitle=f"Daily kWh for {nmi} ({kind})",
        how=None,
        vmin=vmin,
        vmax=vmax,
        cmap="YlOrRd",
        daylabels="MTWTFSS",
        colorbar=True,
    )
    fig = plot[0]
    file_path = Path(f"build/{nmi}_daily_{kind}.png")
    fig.savefig(file_path, bbox_inches="tight")
    log.info("Created %s", file_path)
    return file_path


def build_daily_plot(nmi: str) -> str:
    """Save calendar plot"""

    day_data = list(get_day_data(nmi))
    data = {
        "morning": [x[3] for x in day_data],
        "day": [x[4] for x in day_data],
        "evening": [x[5] for x in day_data],
        "night": [x[6] for x in day_data],
        "export": [-x[2] for x in day_data],
    }
    index = [x[0] for x in day_data]
    df = pd.DataFrame(index=index, data=data)
    color_dict = {
        "export": "green",
        "morning": "tan",
        "day": "skyblue",
        "evening": "orangered",
        "night": "slategrey",
    }
    fig = px.bar(df, x=df.index, y=list(data.keys()), color_discrete_map=color_dict)
    fig.update_xaxes(
        rangeslider_visible=False,
        rangeselector=dict(
            buttons=list(
                [
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(step="all"),
                ]
            )
        ),
    )
    file_path = Path(f"build/{nmi}_daily_plot.html")
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def build_usage_histogram(nmi: str) -> str:
    """Save heatmap of power usage"""
    df = get_usage_df(nmi)
    df["power"] = df["consumption"] + df["export"]
    df["power"] = df["power"].apply(lambda x: x * 12)
    has_export = True if len(df["export"].unique()) > 1 else False
    colorscale = "Geyser" if has_export else "YlOrRd"
    midpoint = 0.0 if has_export else None
    start, end = get_date_range(nmi)
    numdays = (end - start).days
    nbinsx = numdays
    nbinsy = 96
    fig = px.density_heatmap(
        df,
        x=df.index.date,
        y=df.index.time,
        z=df["power"],
        nbinsx=nbinsx,
        nbinsy=nbinsy,
        histfunc="avg",
        color_continuous_scale=colorscale,
        color_continuous_midpoint=midpoint,
    )
    fig.update_layout(
        xaxis_title=None,
        yaxis_title=None,
        legend_title="kW",
        margin=dict(l=20, r=20, t=20, b=20),
    )

    file_path = Path(f"build/{nmi}_usage_histogram.html")
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def copy_static_data():
    """Copy static file"""
    files = []
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
    yr_avg = round(yr_sum / yr_days, 3)

    summary = {
        "Summer": (a_avg, a_sum),
        "Autumn": (b_avg, b_sum),
        "Winter": (c_avg, c_sum),
        "Spring": (d_avg, d_sum),
        "Export": (d_avg, d_sum),
        "Year": (yr_avg, yr_sum),
    }
    return summary


def get_month_data(nmi: str):
    sql = "SELECT * from monthly_reads where nmi = :nmi"
    return db.query(sql, {"nmi": nmi})


def build_report(nmi: str):
    template = env.get_template("nmi-report.html")
    start, end = get_date_range(nmi)
    fp_imp = build_daily_usage_chart(nmi, "import")
    fp_exp = build_daily_usage_chart(nmi, "export")
    build_daily_usage_chart(nmi, "total")
    has_export = True if fp_exp else None

    """
    ch_daily_fp = build_daily_plot(nmi)
    with open(ch_daily_fp, "r") as fh:
        daily_chart = fh.read()
    """

    ch_tou_fp = build_usage_histogram(nmi)
    with open(ch_tou_fp, "r") as fh:
        tou_chart = fh.read()

    report_data = {
        "start": start,
        "end": end,
        "has_export": has_export,
        "daily_chart": "",
        "tou_chart": tou_chart,
        "imp_overview_chart": fp_imp.name,
        "exp_overview_chart": fp_exp.name if has_export else None,
        "season_data": get_seasonal_data(nmi),
        "month_data": get_month_data(nmi),
    }

    output_html = template.render(nmi=nmi, **report_data)
    file_path = f"build/{nmi}.html"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(output_html)
    logging.info("Created %s", file_path)
    return file_path


def build_index(nmis: List[str]):
    template = env.get_template("index.html")
    output_html = template.render(nmis=nmis)
    file_path = "build/index.html"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(output_html)
    logging.info("Created %s", file_path)
    return file_path


logging.basicConfig(level="INFO")
Path("build").mkdir(exist_ok=True)

env = Environment(loader=FileSystemLoader("templates"))
env.filters["yearmonth"] = format_month

copy_static_data()
nmis = get_nmis(DB_PATH)
for nmi in nmis:
    build_report(nmi)
fp = Path(build_index(nmis)).resolve()
webbrowser.open(fp.as_uri())
