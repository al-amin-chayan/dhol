#!/usr/bin/env python3
"""Loopback-only, bounded Telegram webhook authentication proxy for future core ingress."""

from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import re
import time
import urllib.error
import urllib.request

BODY_LIMIT = 65536
RESPONSE_LIMIT = 262144
PATH = re.compile(r"^/webhook/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$")


def authorize(method, path, token, expected):
    if not PATH.fullmatch(path):
        return 404
    if method != "POST":
        return 405
    if (
        not isinstance(token, str)
        or not expected
        or not hmac.compare_digest(token.encode(), expected.encode())
    ):
        return 401
    return 200


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Handler(BaseHTTPRequestHandler):
    secret = ""
    upstream = "http://127.0.0.1:5678"
    window_start = 0.0
    window_count = 0

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        # Paths and bodies can contain sensitive workflow data; no request logging.
        pass

    def respond(self, status, data=b""):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)
        self.close_connection = True

    def handle_request(self):
        tokens = self.headers.get_all("X-Telegram-Bot-Api-Secret-Token", [])
        result = authorize(
            self.command,
            self.path,
            tokens[0] if len(tokens) == 1 else None,
            self.secret,
        )
        if result != 200:
            self.respond(result)
            return
        now = time.monotonic()
        if now - Handler.window_start >= 60:
            Handler.window_start, Handler.window_count = now, 0
        if Handler.window_count >= 60:
            self.respond(429)
            return
        Handler.window_count += 1
        lengths = self.headers.get_all("Content-Length", [])
        if (
            self.headers.get_all("Transfer-Encoding") is not None
            or len(lengths) != 1
            or not lengths[0].isdigit()
        ):
            self.respond(400)
            return
        length = int(lengths[0])
        if not 0 < length <= BODY_LIMIT:
            self.respond(413)
            return
        self.connection.settimeout(5)
        try:
            body = self.rfile.read(length)
            try:
                document = json.loads(body)
            except (ValueError, RecursionError):
                self.respond(400)
                return
            if len(body) != length or not isinstance(document, dict):
                self.respond(400)
                return
            request = urllib.request.Request(
                self.upstream + self.path,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            opener = urllib.request.build_opener(NoRedirect)
            try:
                response = opener.open(request, timeout=5)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                data = response.read(RESPONSE_LIMIT + 1)
                if len(data) > RESPONSE_LIMIT:
                    self.respond(502)
                else:
                    self.respond(response.status, data)
        except (OSError, ValueError):
            self.respond(502)

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = (
        do_TRACE
    ) = do_CONNECT = handle_request


def main():
    Handler.secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if len(Handler.secret) < 32:
        raise SystemExit(
            "verifying proxy requires a scoped webhook secret of at least 32 characters"
        )
    # Neither bind address nor upstream can be changed to a public origin by environment input.
    with HTTPServer(("127.0.0.1", 5680), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
