from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from app.sources import download_media

BODY = b"x" * 4096
PIECE = 1024


def streaming_client(
    body: bytes = BODY, *, declare_length: bool = True, piece: int = PIECE
) -> httpx.AsyncClient:
    """A server that answers in pieces, so the client really iterates.

    The stub ASGI apps elsewhere cannot do this: httpx buffers a whole ASGI
    response before handing it back, and a download that arrives all at once has
    nothing to report about itself.
    """

    async def pieces() -> AsyncIterator[bytes]:
        for offset in range(0, len(body), piece):
            yield body[offset : offset + piece]

    def handle(_request: httpx.Request) -> httpx.Response:
        headers = {"content-length": str(len(body))} if declare_length else {}
        return httpx.Response(200, headers=headers, content=pieces())

    return httpx.AsyncClient(transport=httpx.MockTransport(handle))


async def test_a_download_reports_how_much_has_arrived(tmp_path: Path) -> None:
    seen: list[tuple[int, int | None]] = []

    async def watch(written: int, declared: int | None) -> None:
        seen.append((written, declared))

    async with streaming_client() as http:
        target = await download_media(
            http, "https://files.test/talk.mp3", tmp_path, 10_000, on_progress=watch
        )

    assert target.read_bytes() == BODY
    assert [written for written, _ in seen] == [1024, 2048, 3072, 4096]
    assert {declared for _, declared in seen} == {len(BODY)}


async def test_a_server_that_declares_no_length_says_so(tmp_path: Path) -> None:
    """Content-Length is optional, and a chunked response has none at all. Bytes
    with nothing to divide by are not a percentage, and pretending otherwise
    would mean inventing the total."""
    seen: list[int | None] = []

    async def watch(_written: int, declared: int | None) -> None:
        seen.append(declared)

    async with streaming_client(declare_length=False) as http:
        await download_media(
            http, "https://files.test/talk.mp3", tmp_path, 10_000, on_progress=watch
        )

    assert seen and set(seen) == {None}
