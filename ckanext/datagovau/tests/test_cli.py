from typing import Any

import pytest

import ckan.model as model
from ckan.model.core import State
from ckan.tests import factories

from ckanext.datagovau.cli.maintain import purge_deleted_users


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDgaUserPurge:
    def test_without_args(self, cli):
        """Calling command without args must
        trigger purging all the deleted users"""
        result = cli.invoke(purge_deleted_users)

        assert "There are no deleted users" in result.output
        assert not result.exit_code

    def test_with_fake_user(self, cli):
        """If user doesn't exists, it will be skipped"""
        real_user: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore
        result = cli.invoke(purge_deleted_users, ["test-user", real_user["name"]])

        assert "User <test-user> doesn't exists" in result.output
        assert f"User <{real_user['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_purge_only_specific_user(self, cli):
        """We could provide multiple user ids/names to purge only them"""
        user: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert f"User <{user['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_purge_not_deleted_user(self, cli):
        """Not deleted user musn't be purged"""
        user: dict[str, Any] = factories.User()  # type: ignore

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert (
            f"The user <{user['name']}> is not deleted and cannot be purged"
            in result.output
        )
        assert not result.exit_code
        assert model.Session.query(model.User).filter_by(id=user["id"]).all()

    def test_purge_multiple_specific_users(self, cli):
        """You can specify multiple users to purge"""
        user1: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore
        user2: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore

        result = cli.invoke(purge_deleted_users, [user1["name"], user2["name"]])

        assert f"User <{user1['name']}> has been purged" in result.output
        assert f"User <{user2['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_purge_using_both_id_and_name(self, cli):
        """You can use both ID and username"""
        user1: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore
        user2: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore

        result = cli.invoke(purge_deleted_users, [user1["name"], user2["id"]])

        assert f"User <{user1['name']}> has been purged" in result.output
        assert f"User <{user2['name']}> has been purged" in result.output
        assert not result.exit_code

    def test_user_purge_purges_users(self, cli):
        """Purge command really purges user from database"""
        user1: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore
        user2: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore

        result = cli.invoke(purge_deleted_users, [user1["name"], user2["name"]])

        for user_id in (user1["id"], user2["id"]):
            assert not model.Session.query(model.User).filter_by(id=user_id).all()

    def test_purge_impossible_because_of_memberships(self, cli):
        """User can't be purged if he is a member of group/org"""
        user: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore
        factories.Group(user=user)

        result = cli.invoke(purge_deleted_users, [user["name"]])
        assert (
            f"User <{user['name']}> is a member of groups/organizations"
            in result.output
        )
        assert f"The user <{user['name']}> cannot be purged" in result.output
        assert not result.exit_code

        assert model.Session.query(model.User).filter_by(id=user["id"]).all()

    def test_purge_impossible_because_of_datasets(self, cli):
        """User can't be purged if he has datasets"""
        user: dict[str, Any] = factories.User(state=State.DELETED)  # type: ignore
        factories.Dataset(user=user)

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
