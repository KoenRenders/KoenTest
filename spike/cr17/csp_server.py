"""CR-17 spike (#1626) — a minimal file server with a strict CSP.

Serves the spike worktree root so the page and the vendored bundle come from
one origin, with exactly the policy the spike must prove TipTap works under:

    Content-Security-Policy: default-src 'self'

No unsafe-inline, no unsafe-eval, no nonce, no hash. Every inline script or
style attribute on a page would therefore be blocked — which is the point:
the measurement is which of those TipTap turns out to need.
"""

import sys
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer

CSP = "default-src 'self'"


class CspHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Security-Policy", CSP)
        super().end_headers()


def main():
    root = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8899
    handler = lambda *args, **kwargs: CspHandler(*args, directory=root, **kwargs)
    with TCPServer(("127.0.0.1", port), handler) as httpd:
        print(f"serving {root} on http://127.0.0.1:{port} with CSP: {CSP}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    main()
