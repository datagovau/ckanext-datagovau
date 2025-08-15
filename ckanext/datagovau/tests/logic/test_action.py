from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

from ckan.tests.helpers import call_action


@pytest.mark.usefixtures(
    "with_plugins", "clean_redis", "clean_db", "with_request_context"
)
class TestNotifyAboutArchival:
    def test_notifications(
        self,
        dataset_factory: Any,
        user: dict[str, Any],
        organization: dict[str, Any],
        fake_mailer: mock.Mock,
    ):
        """Notification contains archived datasets."""
        archived = dataset_factory(user=user, owner_org=organization["id"])
        normal = dataset_factory(user=user, owner_org=organization["id"])
        call_action(
            "package_patch", {"user": user["name"]}, id=archived["id"], archived=True
        )

        call_action("dga_notify_about_archival")

        fake_mailer.assert_called_once()
        body = fake_mailer.call_args.kwargs["body"]

        assert archived["title"] in body
        assert normal["title"] not in body
