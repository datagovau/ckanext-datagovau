from typing import Any

import pytest

import ckan.model as model
from ckan.model.core import State

from ckanext.datagovau.cli.maintain import purge_deleted_users


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDgaUserPurge:
    def test_without_args(self, cli: Any):
        """Calling command without args triggers purging all the deleted users."""
        result = cli.invoke(purge_deleted_users)

        assert "There are no deleted users" in result.output
        assert not result.exit_code

    def test_with_fake_user(self, cli: Any, user_factory: Any):
        """If user doesn't exists, it will be skipped."""
        real_user: dict[str, Any] = user_factory(state=State.DELETED)
        result = cli.invoke(purge_deleted_users, ["test-user", real_user["name"]])

        assert "User <test-user> doesn't exists" in result.output
        assert f"User <{real_user['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_purge_only_specific_user(self, cli: Any, user_factory: Any):
        """We could provide multiple user ids/names to purge only them."""
        user: dict[str, Any] = user_factory(state=State.DELETED)

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert f"User <{user['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_purge_not_deleted_user(self, cli: Any, user_factory: Any):
        """Not deleted user musn't be purged."""
        user: dict[str, Any] = user_factory()

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert (
            f"The user <{user['name']}> is not deleted and cannot be purged"
            in result.output
        )
        assert not result.exit_code
        assert model.Session.query(model.User).filter_by(id=user["id"]).all()

    def test_purge_multiple_specific_users(self, cli: Any, user_factory: Any):
        """You can specify multiple users to purge."""
        user1: dict[str, Any] = user_factory(state=State.DELETED)
        user2: dict[str, Any] = user_factory(state=State.DELETED)

        result = cli.invoke(purge_deleted_users, [user1["name"], user2["name"]])

        assert f"User <{user1['name']}> has been purged" in result.output
        assert f"User <{user2['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_purge_using_both_id_and_name(self, cli: Any, user_factory: Any):
        """You can use both ID and username."""
        user1: dict[str, Any] = user_factory(state=State.DELETED)
        user2: dict[str, Any] = user_factory(state=State.DELETED)

        result = cli.invoke(purge_deleted_users, [user1["name"], user2["id"]])

        assert f"User <{user1['name']}> has been purged" in result.output
        assert f"User <{user2['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_user_purge_purges_users(self, cli: Any, user_factory: Any):
        """Purge command really purges user from database."""
        user1: dict[str, Any] = user_factory(state=State.DELETED)
        user2: dict[str, Any] = user_factory(state=State.DELETED)

        cli.invoke(purge_deleted_users, [user1["name"], user2["name"]])

        for user_id in (user1["id"], user2["id"]):
            assert not model.Session.query(model.User).filter_by(id=user_id).all()

    def test_purge_impossible_because_of_memberships(
        self, cli: Any, group_factory: Any, user_factory: Any
    ):
        """User can't be purged if he is a member of group/org."""
        user: dict[str, Any] = user_factory(state=State.DELETED)
        group_factory(user=user)

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert (
            f"User <{user['name']}> is a member of groups/organizations"
            in result.output
        )
        assert f"The user <{user['name']}> cannot be purged" in result.output
        assert not result.exit_code

        assert model.Session.query(model.User).filter_by(id=user["id"]).all()

    def test_purge_impossible_because_of_datasets(
        self, cli: Any, dataset_factory: Any, user_factory: Any
    ):
        """User can't be purged if he has datasets."""
        user: dict[str, Any] = user_factory(state=State.DELETED)
        dataset_factory(user=user)

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert (
            f"There are 1 datasets created by <{user['name']}> user." in result.output
        )
        assert (
            f"The user <{user['name']}> is mentioned in 1 package activities"
            in result.output
        )
        assert f"The user <{user['name']}> cannot be purged" in result.output
        assert not result.exit_code
        assert model.Session.query(model.User).filter_by(id=user["id"]).all()
