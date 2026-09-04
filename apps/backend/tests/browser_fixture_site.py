from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit


@dataclass
class LocalMarketplace:
    """Loopback-only deterministic marketplace used by Playwright integration tests."""

    plans: tuple[dict[str, object], ...] = (
        {"name": "Starter", "price": "$10/month", "sso": "No", "users": 5},
        {"name": "Pro", "price": "$20/month", "sso": "Yes", "users": 10},
        {"name": "Business", "price": "$30/month", "sso": "Yes", "users": 25},
    )
    _server: ThreadingHTTPServer | None = field(init=False, default=None)
    _thread: Thread | None = field(init=False, default=None)
    _commit_count: int = field(init=False, default=0)
    _lock: Lock = field(init=False, default_factory=Lock)

    @property
    def origin(self) -> str:
        if self._server is None:
            raise RuntimeError("Local marketplace is not running.")
        return f"http://127.0.0.1:{self._server.server_port}"

    def url(self, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("Fixture paths must be absolute.")
        return f"{self.origin}{path}"

    def start(self) -> None:
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                path = urlsplit(self.path)
                if path.path == "/":
                    self._html(fixture._pricing_page())
                    return
                if path.path == "/review":
                    plan = parse_qs(path.query).get("plan", [""])[0]
                    self._html(fixture._review_page(plan))
                    return
                self.send_error(404)

            def do_POST(self) -> None:  # noqa: N802
                if urlsplit(self.path).path != "/commit":
                    self.send_error(404)
                    return
                with fixture._lock:
                    fixture._commit_count += 1
                self._html(fixture._confirmation_page())

            def _html(self, body: str) -> None:
                payload = body.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, _format: str, *args) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    async def commit_count(self) -> int:
        with self._lock:
            return self._commit_count

    def _pricing_page(self) -> str:
        cards = "".join(
            (
                "<article aria-label=\"{name} plan\">"
                "<h2>{name}</h2><p>{price}</p><p>SSO: {sso}</p>"
                "<p>Users: {users}</p>"
                "<a href=\"/review?plan={slug}\"><button>Choose {name}</button></a>"
                "</article>"
            ).format(
                name=escape(str(plan["name"])),
                price=escape(str(plan["price"])),
                sso=escape(str(plan["sso"])),
                users=escape(str(plan["users"])),
                slug=escape(str(plan["name"]).lower()),
            )
            for plan in self.plans
        )
        return f"<html><head><title>Marketplace</title></head><body><main><h1>Plans</h1>{cards}</main></body></html>"

    def _review_page(self, plan_slug: str) -> str:
        plan = next(
            (item for item in self.plans if str(item["name"]).lower() == plan_slug),
            None,
        )
        if plan is None:
            return "<html><body><h1>Unknown plan</h1></body></html>"
        name = escape(str(plan["name"]))
        return (
            "<html><head><title>Review signup</title></head><body><main>"
            f"<h1>Review {name} signup</h1>"
            f"<p>{escape(str(plan['price']))} - SSO: {escape(str(plan['sso']))} - Users: {escape(str(plan['users']))}</p>"
            "<form method=\"post\" action=\"/commit\" aria-label=\"Signup review\">"
            "<label>Name <input name=\"name\" type=\"text\"></label>"
            f"<input name=\"plan\" type=\"hidden\" value=\"{name}\">"
            f"<button type=\"submit\">Confirm {name} signup</button>"
            "</form></main></body></html>"
        )

    @staticmethod
    def _confirmation_page() -> str:
        return "<html><head><title>Signup complete</title></head><body><main><h1>Signup complete</h1><p>Test signup recorded.</p></main></body></html>"
