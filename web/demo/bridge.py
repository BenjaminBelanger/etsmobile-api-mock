import importlib
import json
import traceback
from urllib.parse import unquote

import anyio.to_thread


async def run_sync_inline(func, *args, **_options):
    return func(*args)


def load_app():
    anyio.to_thread.run_sync = run_sync_inline
    return importlib.import_module("main").app


async def handle(app, method, url, headers, body):
    path, _, query = url.partition("?")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": unquote(path),
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": [
            (name.lower().encode(), value.encode())
            for name, value in json.loads(headers)
        ],
        "client": ("127.0.0.1", 0),
        "server": ("demo", 443),
    }
    unread = [{"type": "http.request", "body": body.encode(), "more_body": False}]
    response = {"status": None, "headers": [], "body": b""}

    async def receive():
        return unread.pop() if unread else {"type": "http.disconnect"}

    async def send(message):
        if message["type"] == "http.response.start":
            response["status"] = message["status"]
            response["headers"] = [
                (name.decode(), value.decode()) for name, value in message["headers"]
            ]
        elif message["type"] == "http.response.body":
            response["body"] += message.get("body", b"")

    try:
        await app(scope, receive, send)
    except Exception:
        if response["status"] is None:
            raise
        traceback.print_exc()
    return json.dumps(
        {
            "status": response["status"],
            "headers": response["headers"],
            "body": response["body"].decode("utf-8", "replace"),
        }
    )
