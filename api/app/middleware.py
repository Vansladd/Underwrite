from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.services.pdf_text import MAX_UPLOAD_BYTES, PdfTooLarge


class _BodyTooLarge(Exception):
    pass


class LimitBodySize:
    """Refuse an oversized request body before anything downstream reads it.

    Pure ASGI rather than a FastAPI middleware because it has to count bytes off the wire: a
    chunked request declares no `Content-Length`, so a header check alone lets it through to
    Starlette's multipart parser, which spools the whole thing to disk. See D-028.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_UPLOAD_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._declared_over_limit(scope):
            await self._refuse(scope, receive, send)
            return

        seen = 0
        oversized = False
        started = False
        replaced = False

        async def counting_receive() -> Message:
            nonlocal seen, oversized
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    oversized = True
                    raise _BodyTooLarge
            return message

        async def watching_send(message: Message) -> None:
            nonlocal started, replaced
            if replaced:
                return
            # FastAPI turns any body-read failure into a 400 "error parsing the body", so the
            # exception below usually never escapes. Correct its answer on the way out instead.
            if oversized and not started and message["type"] == "http.response.start":
                replaced = True
                await self._refuse(scope, receive, send)
                return
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, watching_send)
        except _BodyTooLarge:
            # Only safe to answer if nothing has gone out yet; otherwise the client already has
            # a status line and the truncated body is the honest signal.
            if started or replaced:
                raise
            await self._refuse(scope, receive, send)

    def _declared_over_limit(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit():
                return int(value) > self.max_bytes
        return False

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(status_code=413, content={"detail": str(PdfTooLarge())})
        await response(scope, receive, send)
