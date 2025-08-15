from __future__ import annotations

import datetime
import tempfile

import click
import sqlalchemy as sa

import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib import mailer

from ckanext.check_link.model import Report
from ckanext.collection import shared

from .geoserveringestor import geoserver_ingestor
from .googleanalytics import stats
from .maintain import maintain
from .spatialingestor import spatial_ingestor

__all__ = [
    "dga",
    "geoserver_ingestor",
    "spatial_ingestor",
]


@click.group(short_help="DGA CLI")
@click.help_option("-h", "--help")
def dga():
    pass


dga.add_command(maintain)
dga.add_command(stats)


@dga.command()
@click.option("-o", "--organization", help="Collect report for organization datasets")
@click.argument("emails", nargs=-1)
def send_link_report(organization: str | None, emails: str):
    """Send email with broken links report."""
    if organization:
        org = model.Group.get(organization)
        col = shared.get_collection(
            "check-link-organization-report",
            {},
            data_settings={"organization_id": org.id if org else organization},
        )
    else:
        col = shared.get_collection("check-link-report", {})

    serializer = shared.serialize.CsvSerializer(col)

    body = (
        "Please find attached a CSV file containing a list of broken"
        " links we've identified. This file includes the URLs, along"
        " with any additional details that might help in fixing or replacing them."
    )

    with tempfile.SpooledTemporaryFile(1024**2 * 10, "rb+") as buff:
        with click.progressbar(
            serializer.stream(), label="Collecting links into temporal file"
        ) as bar:
            for line in bar:
                buff.write(line.encode())

        with click.progressbar(
            emails, label="Sending report to specified emails"
        ) as bar:
            for email in bar:
                buff.seek(0)
                mailer.mail_recipient(
                    email,
                    email,
                    "DGA: Broken links",
                    body,
                    attachments=[
                        ("report.csv", buff, "text/csv"),
                    ],
                )


@dga.command()
@click.option("-d", "--dataset", multiple=True, help="Check only specified datasets.")
def archive_datasets(dataset: tuple[str]):
    """Mark unmaintained datasets as archived."""
    resource_count = sa.func.count(model.Resource.id).label("resource_count")
    broken_count = sa.func.count(Report.id).label("broken_count")
    broken_rate = (broken_count * 100 / resource_count).label("broken_rate")
    since_update = (sa.func.now() - model.Package.metadata_modified).label(
        "since_update"
    )

    bound_max_age = tk.config["ckanext.datagovau.archive.days_without_update"]
    bound_broken_max_age = tk.config[
        "ckanext.datagovau.archive.broken_days_without_update"
    ]
    bound_broken_rate = tk.config["ckanext.datagovau.archive.broken_percentage"]

    stmt = (
        sa.select(model.Package.id)
        .outerjoin(
            model.PackageExtra,
            sa.and_(
                model.PackageExtra.package_id == model.Package.id,
                model.PackageExtra.key == "archived",
            ),
        )
        .join(
            model.Resource,
            sa.and_(
                model.Resource.package_id == model.Package.id,
                model.Resource.state == "active",
            ),
        )
        .outerjoin(
            Report,
            Report.resource_id == model.Resource.id,
        )
        .group_by(model.Package)
        .where(
            model.Package.state == "active",
            sa.or_(
                model.PackageExtra.value.is_(None),
                model.PackageExtra.value != "true",
            ),
            sa.or_(
                Report.state != "available",
                Report.state.is_(None),
            ),
        )
        .having(
            sa.or_(
                since_update > datetime.timedelta(days=bound_max_age),
                sa.and_(
                    since_update > datetime.timedelta(days=bound_broken_max_age),
                    broken_rate >= bound_broken_rate,
                ),
            ),
        )
        .order_by(since_update.desc())
    )

    if dataset:
        stmt = stmt.where(
            model.Package.name.in_(dataset) | model.Package.id.in_(dataset)
        )

    total = model.Session.scalar(sa.select(sa.func.count()).select_from(stmt))
    user = tk.get_action("get_site_user")({"ignore_auth": True}, {})

    click.echo(total)
    with click.progressbar(model.Session.scalars(stmt), length=total) as bar:
        for pkg_id in bar:
            try:
                tk.get_action("package_patch")(
                    {"user": user["name"]}, {"id": pkg_id, "archived": True}
                )
            except tk.ValidationError as err:  # noqa: PERF203
                tk.error_shout(f"Cannot update {pkg_id}: {err.error_dict}\n")


@dga.command()
@click.pass_context
def notify_about_archival(ctx: click.Context):
    """Send notification to curators of archived datasets."""
    flask_app = ctx.meta["flask_app"]
    # Email cannot be rendered without context
    with flask_app.test_request_context():
        tk.get_action("dga_notify_about_archival")({"ignore_auth": True}, {})

    click.secho("Done", fg="green")
