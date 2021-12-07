from __future__ import annotations

from typing import Iterable

import click
from ckan import model
import ckan.plugins.toolkit as tk

# datagovau spatial-ingestor command group.
@click.group("spatial-ingestor", short_help="Ingest spatial data")
def spatial_ingestor():
    pass


def ingest_scope(scope) -> Iterable[tuple[str, bool]]:
    if not isinstance(scope, str):
        # it has been normalised already
        yield from scope
    elif scope not in ("all", "updated", "updated-orgs"):
        yield scope, True
    else:
        force = scope == "all"
        query = model.Session.query(model.Package.id).filter_by(state="active")
        if scope == "updated-orgs":
            query = query.filter(
                # TODO: why they are hardcoded? Either fetch them from config
                # file or pass as CLI argument
                model.Package.owner_org.in_(
                    [
                        "3965c5cd-d88f-4735-92db-af28d3ad9155",  # nntt
                        "a56f8067-b250-4c32-9609-f2191dc88a3a",  # geelong
                    ]
                )
            )

        with click.progressbar(query) as bar:
            for pkg in bar:
                yield pkg.id, force


# spatial-ingestor ingest subcommand.
@spatial_ingestor.command("ingest")
@click.argument("scope", type=ingest_scope)
def perform_ingest(scope: Iterable[tuple[str, bool]]):
    """
    Performs ingest of spatial data for scope of data.

    Usage::
        ckan spatial-ingestor <scope>

        where scope is one of: 'all', 'updated', 'updated-orgs', or <dataset-id>.
    """
    from ._spatialingestor import do_ingesting

    for pkg_id, force in scope:
        do_ingesting(pkg_id, force)


def purge_scope(scope) -> Iterable[tuple[str, bool]]:
    from ._spatialingestor import check_if_may_skip, IngestionSkip

    if not isinstance(scope, str):
        # it has been normalised already
        yield from scope
    elif scope not in ["all", "erroneous"]:
        yield scope, False
    else:
        query = model.Session.query(model.Package.id)
        with click.progressbar(query) as bar:
            for pkg in bar:
                if scope == "erroneous":
                    try:
                        check_if_may_skip(pkg.id, True)
                    except IngestionSkip:
                        yield pkg.id, False
                else:
                    yield pkg.id, True


# datagovau spatial-ingestor purge subcommand.
@spatial_ingestor.command("purge")
@click.argument("scope", type=purge_scope)
def perform_purge(scope: Iterable[tuple[str, bool]]):
    """
    Performs purge of nominated scope.

    Usage:
        ckan spatial-ingestor purge <scope>

        where scope is one of: 'all', 'erroneous', or <dataset-id>.
    """
    from ._spatialingestor import clean_assets

    for pkg_id, skip_grids in scope:
        clean_assets(pkg_id, skip_grids=skip_grids)


# datagovau spatial-ingestor dropuser subcommand.
@spatial_ingestor.command("dropuser")
@click.argument("username")
def perform_drop_user(username: str):
    """
    Deletes nominated user.

    Usage:
        ckan spatial-ingestor dropuser <username>
    """
    user: model.User = model.User.get(username)
    if user is None:
        tk.error_shout(f"User <{username}> not found")
        raise click.Abort()

    groups = user.get_groups()
    if groups:
        tk.error_shout(
            "User is a member of groups/organizations: %s"
            % ", ".join(g.display_name for g in groups)
        )
        raise click.Abort()

    pkgs = model.Session.query(model.Package).filter_by(
        creator_user_id=user.id
    )
    if pkgs.count():
        tk.error_shout(
            "There are some(%d) datasets created by this user: %s"
            % (pkgs.count(), [pkg.name for pkg in pkgs])
        )
        raise click.Abort()

    activities = (
        model.Session.query(model.Activity)
        .filter_by(user_id=user.id)
        .filter(model.Activity.activity_type.contains("package"))
    )
    if activities.count():
        tk.error_shout(
            "There are some(%d) activity records that mentions user"
            % activities.count()
        )
        raise click.Abort()

    model.Session.delete(user)
    model.Session.commit()
    click.secho("Done", fg="green")


# Command currently not referenced in any of the DGA
# batch scripts.  Skeleton included in case it is required
# in the future.  This command appears to be something
# of a junkbucked/kludgy solution to a problem that will
# likely need not to be addressed---source code for it is
# in the old commands.py source.
# @click.group('purgelegacyspatial', short_help=u"Cleans out what old spatial ingestor did.")
# def purgelegacyspatial():
#    pass
#
# @purgelegacyspatial.command()
# @click.argument()
# def perform_stuff():
#    """
#    Placeholder for now.
#    """
#    pass
