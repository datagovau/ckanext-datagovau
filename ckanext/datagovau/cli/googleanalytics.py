from __future__ import annotations

import calendar
import re
from datetime import datetime as dt
from typing import Any

import click
from typing_extensions import TypedDict

import ckan.plugins.toolkit as tk
from ckan import model

RE_PKG = re.compile(r"/dataset/(?P<id>[^/?#]+)")
RE_RES = re.compile(r"/dataset/(?P<pkg_id>[^/?#]+)/resource/(?P<res_id>[^/?#]+)")

GA_TYPE_RES = "resource"
GA_TYPE_PKG = "dataset"

PAGE_PATH = 0
PAGE_VIEWS = 1
RES_DOWNLOADS = -1

DGA_STATS = "dga_ga_stats"


class GaData(TypedDict):
    headers: list[str]
    rows: list[list[str]]


class PresentDateError(Exception):
    pass


@click.group("stats", short_help="Google analytic stats")
@click.help_option("-h", "--help")
def stats():
    pass


@stats.command("collect-all")
@click.option(
    "--years",
    type=int,
    default=1,
    help="Fetch GA data for last N years. Default 1",
)
def collect_all(years):
    """Fetch data for last n years."""
    for date in _get_dates_for_last_n_years(years):
        _collect(date)

    _fill_empty_values_for_packages()


def _get_dates_for_last_n_years(years) -> list[str]:
    """Return a list of dates in %Y-%m format."""
    current_year: int = dt.today().year
    current_month: int = dt.today().month

    dates: list[str] = []

    try:
        for year in range(current_year - years + 1, current_year + 1):
            for month in range(1, 13):
                dates.append(f"{year}-{month:02}")

                if (month == current_month) and (year == current_year):
                    raise PresentDateError
    except PresentDateError:
        pass

    return dates


def _fill_empty_values_for_packages():
    user: dict[str, Any] = tk.get_action("get_site_user")({"ignore_auth": True}, {})
    context = {"user": user["name"]}

    current_year: int = dt.today().year
    current_month: int = dt.today().month
    stats = _get_or_create_overall_stats(context)

    for pkg_id, stats_data in stats.items():
        package = model.Package.get(pkg_id)

        creation_year: int = package.metadata_created.year
        creation_month: int = package.metadata_created.month

        try:
            for year in range(creation_year, current_year + 1):
                for month in range(1, 13):
                    if year == creation_year and month < creation_month:
                        continue

                    stats_data.setdefault(
                        f"{year}-{month:02}", {"views": 0, "downloads": 0}
                    )

                    if (month == current_month) and (year == current_year):
                        raise PresentDateError
        except PresentDateError:
            pass

    tk.get_action("flakes_flake_override")(
        context,
        {"data": stats, "name": DGA_STATS},
    )


@stats.command("collect")
def collect():
    """Fetch fresh stats from Google Analytics."""
    _collect(dt.today().strftime("%Y-%m"))
    _fill_empty_values_for_packages()


def _collect(date):
    user: dict[str, Any] = tk.get_action("get_site_user")({"ignore_auth": True}, {})
    context = {"user": user["name"]}

    stats: dict[str, dict[str, int]] = get_stats(date)

    monthly_stats = tk.get_action("flakes_flake_override")(
        context,
        {"data": stats, "name": f"{DGA_STATS}:{date}"},
    )

    update_overall_stats(context, monthly_stats, date)


def get_stats(date: str) -> dict[str, dict[str, int]]:
    """Return parsed stats data from Google Analytics."""
    stats = {}

    parse_views_report(stats, get_dataset_views(date))
    parse_downloads_report(stats, get_resource_downloads(date))

    _fill_stats_with_zeros_if_empty(stats)

    return stats


def parse_views_report(stats, ga_data):
    """Parse dataset views GA report."""
    for row in ga_data["rows"]:
        match = RE_PKG.search(row[PAGE_PATH])

        if not match:
            continue

        pkg_id: str = match.group("id")
        pkg = model.Package.get(pkg_id)

        if not pkg:
            continue

        stats.setdefault(pkg.id, {})
        stats[pkg.id].setdefault("views", 0)
        stats[pkg.id]["views"] += int(row[PAGE_VIEWS])


def parse_downloads_report(stats, ga_data):
    """Parse resource downloads GA report."""
    for row in ga_data["rows"]:
        match = RE_RES.search(row[PAGE_PATH])

        if not match:
            continue

        res_id: str = match.group("res_id")
        pkg_id: str = match.group("pkg_id")

        res = model.Resource.get(res_id)
        pkg = model.Package.get(pkg_id)

        if not res or not pkg:
            continue

        stats.setdefault(pkg.id, {})
        stats[pkg.id].setdefault("downloads", 0)
        stats[pkg.id]["downloads"] += int(row[RES_DOWNLOADS])


def get_dataset_views(date) -> GaData:
    """Return dataset views GA report."""
    data_dict = {
        "dimensions": "ga:pagePath",
        "metrics": "ga:pageviews",
    }

    return _get_stats_data(date, data_dict)


def get_resource_downloads(date) -> GaData:
    """Return resource downloads GA report."""
    data_dict = {
        "dimensions": "ga:pagePath,ga:eventCategory,ga:eventAction",
        "metrics": "ga:totalEvents",
        "category": "Resource",
        "action": "Download",
    }

    return _get_stats_data(date, data_dict)


def _get_stats_data(date, data_dict) -> GaData:
    date_month_start: str = str(dt.strptime(date, "%Y-%m").date())
    year, month = date.split("-")
    last_day: int = calendar.monthrange(int(year), int(month))[1]
    date_last_day: str = str(dt.strptime(f"{date}-{last_day:02}", "%Y-%m-%d").date())

    data_dict["start_date"] = date_month_start
    data_dict["end_date"] = date_last_day

    return tk.get_action("googleanalytics_event_report")(
        {"ignore_auth": True}, data_dict
    )


def update_overall_stats(context, stats: dict[str, Any], date: str):
    """Update overall stats from month stats."""
    overall_stats: dict[str, Any] = _get_or_create_overall_stats(context)

    for pkg_id, data in stats["data"].items():
        overall_stats.setdefault(pkg_id, {})
        overall_stats[pkg_id][date] = data

    tk.get_action("flakes_flake_override")(
        context,
        {"data": overall_stats, "name": DGA_STATS},
    )


def _get_or_create_overall_stats(context) -> dict[str, Any]:
    """Return overall GA stats."""
    try:
        stats = tk.get_action("flakes_flake_lookup")(
            context,
            {"name": DGA_STATS},
        )
    except tk.ObjectNotFound:
        stats = tk.get_action("flakes_flake_create")(
            context,
            {"data": {}, "name": DGA_STATS},
        )

    return stats["data"]


def _fill_stats_with_zeros_if_empty(stats):
    for stat in stats.values():
        stat.setdefault("views", 0)
        stat.setdefault("downloads", 0)
