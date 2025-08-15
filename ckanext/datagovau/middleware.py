from __future__ import annotations

from typing import Any

from flask.json.tag import TaggedJSONSerializer
from flask_session.base import Serializer as FlaskSessionSerializer


class DGARedisSessionSerializer(TaggedJSONSerializer, FlaskSessionSerializer):
    """Adapter of flask's serializer for flask-session.

    This serializer is used instead of MsgPackSerializer from flask-session,
    because the latter cannot handle Markup and raises an exception when flash
    message with HTML added to session.
    """

    def encode(self, session: Any) -> bytes:
        """Serialize the session data."""
        return self.dumps(session).encode()

    def decode(self, serialized_data: bytes) -> Any:
        """Deserialize the session data."""
        return self.loads(serialized_data.decode())
