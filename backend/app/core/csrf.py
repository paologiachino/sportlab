"""CSRF barrier: state-changing API requests must carry X-Requested-With.

The session cookies are already SameSite=Strict, so browsers do not send them
with requests from other sites. As a second barrier, POST/PUT/PATCH/DELETE under
/api/ need a custom header, which a form or a link on another site cannot set
(setting it from JavaScript on another origin would need CORS, which is off).

A middleware rather than a dependency on each endpoint: new endpoints are
covered by default and cannot forget it.
"""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

CSRF_HEADER = "X-Requested-With"
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class RequireCSRFHeader:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] in UNSAFE_METHODS
            and scope["path"].startswith("/api/")
        ):
            headers = dict(scope["headers"])
            if not headers.get(CSRF_HEADER.lower().encode()):
                response = JSONResponse(
                    {"detail": f"Missing {CSRF_HEADER} header"}, status_code=403
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
