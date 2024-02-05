import logging
import shutil
import webbrowser
from calendar import monthrange
from datetime import datetime, time
from pathlib import Path
from typing import List, Optional


import calplot
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from nemreader import extend_sqlite
from nemreader.output_db import get_nmis

from .model import (
    DB_PATH,
    db,
    get_annual_data,
    get_date_range,
    get_day_data,
    get_day_profile,
    get_day_profiles,
    get_season_data,
    get_usage_df,
)
from .prepare_db import update_nem_database

log = logging.getLogger(__name__)
this_dir = Path(__file__).parent
template_dir = this_dir / "templates"
env = Environment(loader=FileSystemLoader(template_dir))
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)


def format_month(dt: datetime) -> str:
    return dt.strftime("%b %Y")


env.filters["yearmonth"] = format_month


def build_daily_usage_chart(nmi: str, kind: str) -> Optional[Path]:
    """Save calendar plot"""
    days = []
    data = []
    for (
        dt,
        imp,
        exp,
    ) in get_day_data(nmi):
        days.append(dt)
        if kind == "import":
            data.append(imp)
        elif kind == "export":
            data.append(exp)
        elif kind == "total":
            exp = -exp  # Make export negative
            val = imp + exp
            data.append(val)
        else:
            raise ValueError("Invalid usage chart kind")

    if kind == "export":
        if max(data) == 0.0:
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
    file_path = output_dir / f"{nmi}_daily_{kind}.png"
    fig.savefig(file_path, bbox_inches="tight")
    log.info("Created %s", file_path)
    return file_path


def average_daily_profiles_fig(nmi: str) -> go.Figure:
    try:
        df = get_day_profile(nmi)
    except ValueError:
        return ""
    # trace = go.Scatter(x=df["time"], y=df["Avg kW"], name="Avg kW")
    traces = []
    color_dict = {
        "SUMMER": "red",
        "AUTUMN": "green",
        "WINTER": "blue",
        "SPRING": "purple",
    }
    for season in ["SUMMER", "AUTUMN", "WINTER", "SPRING"]:
        if season in df:
            color = color_dict[season]
            trace = go.Scatter(
                x=df["time"], y=df[season], name=season, marker=dict(color=color)
            )
            traces.append(trace)
    fig = go.Figure(data=traces)
    x_values = ["04:00", "09:00", "16:00", "21:00"]
    for x in x_values:
        fig.add_vline(x=x, line_width=1, line_dash="dash", line_color="black")
    fig.update_layout(
        legend=dict(orientation="h", yanchor="top", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(dtick=12)
    return fig

def build_day_profile_plot(nmi: str) -> str:
    """Save profile plot"""
  
    fig = average_daily_profiles_fig(nmi)
    file_path = output_dir / f"{nmi}_day_profile.html"
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def usage_histogram(nmi: str) -> go.Figure:
    df = get_day_profiles(nmi)
    fig = px.histogram(df, x="Avg kW", log_y=True)
    return fig


def build_histogram_plot(nmi: str) -> str:
    """Save profile plot"""
    fig = usage_histogram(nmi)
    file_path = output_dir / f"{nmi}_histogram.html"
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def build_days_profiles_plot(nmi: str) -> str:
    """Save profile plot"""
    df = get_day_profiles(nmi)
    fig = px.line(df, x="time", y="Avg kW", color="day")
    x_values = ["04:00", "09:00", "16:00", "21:00"]
    for x in x_values:
        fig.add_vline(x=x, line_width=1, line_dash="dash", line_color="black")
    fig.update_xaxes(dtick=12)
    fig.update_traces(line_color="royalblue", showlegend=False)
    file_path = output_dir / f"{nmi}_days_profiles.html"
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def daily_total_fig(nmi: str) -> go.Figure:
    day_data = list(get_day_data(nmi))
    data = {
        "import": [x[1] for x in day_data],
        "export": [-x[2] for x in day_data],
    }
    index = [x[0] for x in day_data]
    df = pd.DataFrame(index=index, data=data)
    color_dict = {
        "export": "green",
        "import": "orangered",
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
    fig.update_layout(
        xaxis_title=None,
        yaxis_title="kWh",
    )
    return fig



def build_daily_plot(nmi: str) -> str:
    """Save daily totals plot"""

    fig = daily_total_fig(nmi)
    file_path = output_dir / f"{nmi}_daily_totals.html"
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def usage_heatmap(nmi: str) -> go.Figure:

    df = get_usage_df(nmi)
    df["power"] = df["consumption"] + df["export"]
    df["power"] = df["power"].apply(lambda x: x * 12)
    has_export = True if len(df["export"].unique()) > 1 else False
    colorscale = "Geyser" if has_export else "YlOrRd"
    midpoint = 0.0 if has_export else None
    start, end = get_date_range(nmi)
    numdays = (end - start).days
    nbinsx = 96
    nbinsy = numdays
    width = 800
    height = 200 + int(numdays * 0.5)
    fig = px.density_heatmap(
        df,
        width=width,
        height=height,
        x=df.index.time,
        y=df.index.date,
        z=df["power"],
        nbinsx=nbinsx,
        nbinsy=nbinsy,
        histfunc="avg",
        color_continuous_scale=colorscale,
        color_continuous_midpoint=midpoint,
    )

    datemin = min(df.index.date)
    datemax = max(df.index.date)
    x_values = [time(4, 0), time(9, 0), time(16, 0), time(21, 0)]
    for x in x_values:
        fig.add_shape(
            type="line",
            x0=x,
            y0=datemin,
            x1=x,
            y1=datemax,
            line=dict(color="black", width=1, dash="dash"),
        )

    fig.update_layout(
        xaxis_title=None,
        yaxis_title=None,
        margin=dict(l=20, r=20, t=20, b=20),
    )
    fig.update_layout(coloraxis=dict(colorbar=dict(title="kW")))
    fig.update_yaxes(dtick="M1", tickformat="%b\n%Y", ticklabelmode="period")
    fig.update_xaxes(dtick=12, tickformat="%H:%M")
    return fig

def build_usage_heatmap(nmi: str) -> str:
    """Save heatmap of power usage"""
  
    fig = usage_heatmap(nmi)
    file_path = output_dir / f"{nmi}_usage_heatmap.html"
    fig.write_html(file_path, full_html=False, include_plotlyjs="cdn")
    log.info("Created %s", file_path)
    return file_path


def copy_static_data():
    """Copy static files"""
    files = []
    for file in files:
        from_loc = template_dir / file
        to_loc = output_dir / file
        shutil.copy(from_loc, to_loc)


def get_seasonal_data(nmi: str):
    season_data = {}
    all_exp = 0
    all_imp = 0
    total_days = 0
    for row in get_season_data(nmi):
        season = row["Season"]
        num_days = row["num_days"]
        imp = row["imp"]
        exp = row["exp"]
        all_imp += imp
        all_exp += exp
        total_days += num_days
        season_data[season] = imp / num_days

    season_data["EXPORT"] = all_exp / total_days
    season_data["TOTAL"] = all_imp / total_days
    return season_data


def get_month_data(nmi: str):
    sql = "SELECT * from monthly_reads where nmi = :nmi"
    rows = []
    for row in db.query(sql, {"nmi": nmi}):
        month_desc = row["month"]
        num_days = row["num_days"]
        year, month = [int(x) for x in month_desc.split("-")]
        _, exp_num_days = monthrange(year, month)
        row["incomplete"] = True if num_days < exp_num_days else False
        rows.append(row)
    return rows




def build_report(nmi: str, static_mode: bool = True):
    template = env.get_template("nmi-report.html")
    start, end = get_date_range(nmi)
    fp_imp = build_daily_usage_chart(nmi, "import")
    fp_exp = build_daily_usage_chart(nmi, "export")

    build_daily_usage_chart(nmi, "total")
    has_export = True if fp_exp else None

    ch_daily_fp = build_daily_plot(nmi)
    with open(ch_daily_fp, "r") as fh:
        daily_chart = fh.read()

    ch_tou_fp = build_usage_heatmap(nmi)
    with open(ch_tou_fp, "r") as fh:
        tou_chart = fh.read()

    profile_fp = build_day_profile_plot(nmi)
    if profile_fp:
        with open(profile_fp, "r") as fh:
            profile_chart = fh.read()
    else:
        profile_chart = ""

    profiles_fp = build_days_profiles_plot(nmi)
    with open(profiles_fp, "r") as fh:
        profiles_chart = fh.read()

    histogram_fp = build_histogram_plot(nmi)
    with open(histogram_fp, "r") as fh:
        histogram_chart = fh.read()

    report_data = {
        'static_mode': static_mode,
        "start": start,
        "end": end,
        "has_export": has_export,
        "daily_chart": daily_chart,
        "tou_chart": tou_chart,
        "profile_chart": profile_chart,
        "profiles_chart": profiles_chart,
        "histogram_chart": histogram_chart,
        "imp_overview_chart": fp_imp.name,
        "exp_overview_chart": fp_exp.name if has_export else None,
        "season_data": get_seasonal_data(nmi),
        "annual_data": get_annual_data(nmi),
        "month_data": get_month_data(nmi),
    }

    output_html = template.render(nmi=nmi, **report_data)
    file_path = output_dir / f"{nmi}.html"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(output_html)
    logging.info("Created %s", file_path)
    return file_path


def build_index(nmis: List[str]):
    template = env.get_template("index.html")
    output_html = template.render(nmis=nmis)
    file_path = output_dir / "index.html"
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(output_html)
    logging.info("Created %s", file_path)
    return file_path


def build_reports():
    if "daily_reads" not in db.table_names():
        update_nem_database()
    extend_sqlite(DB_PATH)
    copy_static_data()
    nmis = get_nmis(DB_PATH)
    for nmi in nmis:
        build_report(nmi)
    fp = Path(build_index(nmis)).resolve()
    webbrowser.open(fp.as_uri())
    return fp
