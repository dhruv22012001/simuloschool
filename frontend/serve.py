#!/usr/bin/env python3
"""Local dev server for the static frontend.

Identical to `python -m http.server`, except it tells the browser never to
cache. Plain http.server lets the browser hold on to HTML, so edits appear not
to take effect until a hard refresh — this removes that whole class of
confusion during development.

    python3 serve.py [port]        # defaults to 5500
"""

import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5500


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_head(self):
        # Drop the browser's revalidation headers so we never answer 304 and
        # always send fresh bytes. (HTTPMessage supports __delitem__, not pop.)
        for header in ("If-Modified-Since", "If-None-Match"):
            del self.headers[header]
        return super().send_head()


if __name__ == "__main__":
    print(f"Serving ./ at http://localhost:{PORT}  (caching disabled)")
    ThreadingHTTPServer(("", PORT), NoCacheHandler).serve_forever()
