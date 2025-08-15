import time

import pyotp
import pytest

from ckanext.security.model import ReplayAttackException, SecurityTOTP


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTOTPReplayProtection:
    @pytest.mark.usefixtures("with_plugins", "clean_db", "with_request_context")
    def test_same_token_cannot_be_reused(self, user):
        """Second use of the same token must raise ReplayAttackException."""
        challenger = SecurityTOTP.create_for_user(user["name"])
        secret = challenger.secret

        totp = pyotp.TOTP(secret)

        token = totp.now()
        assert challenger.check_code(token) is True  # first use succeeds

        SecurityTOTP.Session.flush()
        SecurityTOTP.Session.refresh(challenger)

        with pytest.raises(ReplayAttackException):
            challenger.check_code(token)

    def test_new_token_accepted(self, user):
        """A fresh token in the next 30-second window is accepted."""
        challenger = SecurityTOTP.create_for_user(user["name"])
        totp = pyotp.TOTP(challenger.secret)

        first_code = totp.now()
        assert challenger.check_code(first_code) is True

        time_remaining = 30 - (int(time.time()) % 30)
        time.sleep(time_remaining + 1)

        next_code = totp.now()
        assert next_code != first_code
        assert challenger.check_code(next_code) is True
