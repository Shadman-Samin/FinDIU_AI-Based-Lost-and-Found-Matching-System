from starlette.responses import JSONResponse


class RequestSizeLimit:
    """Bound the actual streamed body, including requests without Content-Length."""

    def __init__(self, app, max_bytes=6 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        total = 0
        too_large = False
        started = False

        async def bounded_receive():
            nonlocal total, too_large
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    too_large = True
                    # Let the multipart parser unwind and close temporary uploads.
                    from starlette.formparsers import MultiPartException

                    raise MultiPartException("Request too large")
            return message

        async def bounded_send(message):
            nonlocal started
            if too_large and not started:
                started = True
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "request_too_large",
                            "message": "Request exceeds the size limit.",
                        }
                    },
                )
                await response(scope, receive, send)
            elif not too_large:
                await send(message)

        await self.app(scope, bounded_receive, bounded_send)
