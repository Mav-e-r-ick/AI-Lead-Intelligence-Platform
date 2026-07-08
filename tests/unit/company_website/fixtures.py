"""Shared HTML fixtures and a MockTransport-backed httpx.Client builder for
the Company Website Provider's tests."""

from __future__ import annotations

from typing import Callable

import httpx

HOMEPAGE_WITH_LEADERSHIP_LINK = """
<html><body>
  <nav>
    <a href="/products">Products</a>
    <a href="/leadership">Leadership</a>
  </nav>
</body></html>
"""

HOMEPAGE_WITH_NO_LEADERSHIP_LINK = """
<html><body>
  <nav>
    <a href="/products">Products</a>
    <a href="/contact">Contact</a>
  </nav>
</body></html>
"""

LEADERSHIP_PAGE_ONE_EXECUTIVE = """
<html><body>
  <div class="team-member">
    <h2 class="name">Ada Lovelace</h2>
    <p class="title">Chief Executive Officer</p>
  </div>
</body></html>
"""

LEADERSHIP_PAGE_TWO_EXECUTIVES = """
<html><body>
  <div class="team-member">
    <h2 class="name">Ada Lovelace</h2>
    <p class="title">Chief Executive Officer</p>
  </div>
  <div class="team-member">
    <h2 class="name">Grace Hopper</h2>
    <p class="title">Chief Technology Officer</p>
  </div>
</body></html>
"""

ROBOTS_DISALLOW_ALL = "User-agent: *\nDisallow: /\n"
ROBOTS_DISALLOW_LEADERSHIP = "User-agent: *\nDisallow: /leadership\n"
ROBOTS_ALLOW_ALL = "User-agent: *\nAllow: /\n"


def build_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    """An httpx.Client whose requests are answered entirely by `handler`,
    never touching the real network."""

    return httpx.Client(transport=httpx.MockTransport(handler))


def path_router(
    routes: dict[str, httpx.Response]
) -> Callable[[httpx.Request], httpx.Response]:
    """A simple handler: dispatches by `request.url.path`, 404s anything
    not listed."""

    def handler(request: httpx.Request) -> httpx.Response:
        return routes.get(request.url.path, httpx.Response(404))

    return handler
