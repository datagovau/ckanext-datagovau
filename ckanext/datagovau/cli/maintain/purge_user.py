from __future__ import annotations

import click

from ckan import model
from ckan.model import core

import ckanext.activity.model as activity_model


@click.command()
@click.argument("user_ids", nargs=-1)
def purge_deleted_users(user_ids: tuple[str] | None = None):
    """Purge deleted users if it's safe to delete.

    Args:
        user_ids: tuple of user ids/names. Purges all if not provided
    """
    if not user_ids:
        return _purge_all_deleted_users()

    for user_id in user_ids:
        user: model.User | None = _get_user_obj(user_id)

        if not user:
            click.secho(f"User <{user_id}> doesn't exists")
            continue

        _purge_user(user)


def _purge_all_deleted_users() -> None:
    deleted_users: list[model.User] = _get_deleted_user_list()

    if not deleted_users:
        return click.secho("There are no deleted users", fg="green")

    click.secho(f"Found {len(deleted_users)} deleted users. Trying to purge")

    for user in deleted_users:
        _purge_user(user)


def _get_user_obj(user_id: str) -> model.User | None:
    return model.User.get(user_id)


def _get_deleted_user_list() -> list[model.User]:
    return model.Session.query(model.User).filter_by(state=core.State.DELETED).all()


def _purge_user(user: model.User) -> None:
    if not user.is_deleted():
        return click.secho(
            f"The user <{user.name}> is not deleted and cannot be purged"
        )

    if not _is_safe_to_purge(user):
        return click.secho(f"The user <{user.name}> cannot be purged", fg="red")

    model.Session.delete(user)
    model.Session.commit()

    click.secho(f"User <{user.name}> has been purged")


def _is_safe_to_purge(user: model.User) -> bool:
    return not any(
        (
            _if_user_member_of_group(user),
            _is_user_has_packages(user),
            _if_user_mentioned_in_package_activities(user),
        )
    )


def _if_user_member_of_group(user: model.User) -> bool:
    """Check if user is a member of group/organization."""
    user_groups: list[model.Group] = user.get_groups()

    if user_groups:
        click.secho(
            f"User <{user.name}> is a member of groups/organizations:"
            f" {', '.join(g.title or g.name for g in user_groups)}"
        )

    return bool(user_groups)


def _is_user_has_packages(user: model.User) -> bool:
    """Check if deleted user has datasets."""
    packages_query = model.Session.query(model.Package).filter_by(
        creator_user_id=user.id
    )

    pkg_count: int = packages_query.count()

    if pkg_count:
        click.secho(
            f"There are {pkg_count} datasets created by <{user.name}> user."
            " List of datasets:"
            f" {', '.join(pkg.name for pkg in packages_query)}"
        )

    return bool(pkg_count)


def _if_user_mentioned_in_package_activities(user: model.User) -> bool:
    """Check if user is mentioned in package activities."""
    activities_query = (
        model.Session.query(activity_model.Activity)
        .filter_by(user_id=user.id)
        .filter(activity_model.Activity.activity_type.contains("package"))
    )

    activity_count: int = activities_query.count()

    if activity_count:
        click.secho(
            f"The user <{user.name}> is mentioned in {activity_count} package"
            " activities"
        )

    return bool(activity_count)
