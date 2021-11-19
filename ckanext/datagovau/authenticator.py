from __future__ import annotations

from typing import Any, Optional
from ckan.lib.authenticator import UsernamePasswordAuthenticator
import ckan.model as model

class UsernameEmailPasswordAuthenticator(UsernamePasswordAuthenticator):
    def authenticate(self, environ: dict[str, Any], identity: dict[str, Any]) -> Optional[str]:
        if "login" in identity:
            user = model.Session.query(model.User.name).filter_by(email=identity["login"]).first()
            if user:
                identity["login"] = user.name

        return super().authenticate(environ, identity)
