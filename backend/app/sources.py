"""Where the media of a job comes from.

Two kinds of link, told apart before anything is fetched: a direct file we can
stream ourselves, and a page that needs an extractor. Guessing wrong is cheap in
one direction only -- handing a page to httpx yields HTML that ffmpeg rejects --
so the rule is deliberately narrow: only a known media extension is a file.
"""

import asyncio
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

import httpx

from app.errors import ApiError
from app.media import run

SourceType = str  # upload | remote_url | ytdlp

MEDIA_SUFFIXES = frozenset(
    {
        ".aac", ".aiff", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav", ".wma",
        ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".ts", ".webm", ".wmv",
    }
)


def parse_source_url(raw: str) -> tuple[SourceType, str]:
    """Validate a submitted link and decide who fetches it.

    Returns the source type and the name to show until something better is
    known: a filename for a direct link, the link itself for a page, whose real
    title only arrives with the metadata yt-dlp reads.
    """
    url = raw.strip()
    parsed = urlparse(url)

    # http only. file:// would read the server's own disk, and every other
    # scheme is either unreachable from here or someone probing.
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiError(400, "invalid_url", "That is not an http or https link.", url=url)

    name = PurePosixPath(unquote(parsed.path)).name
    if name and PurePosixPath(name).suffix.lower() in MEDIA_SUFFIXES:
        return "remote_url", name
    return "ytdlp", url


async def ensure_allowed_host(url: str, *, allow_private: bool) -> None:
    """Refuse links that point back inside the network the server sits in.

    Fetching a link on someone's behalf makes the server a proxy, and an account
    on this instance must not become a way to read a cloud metadata endpoint, a
    router's admin page, or which ports on the host answer at all. Operators who
    genuinely want to pull from their own NAS turn the check off.
    """
    if allow_private:
        return

    host = urlparse(url).hostname
    if not host:
        raise ApiError(400, "invalid_url", "That link has no host.", url=url)

    try:
        resolved = await asyncio.get_running_loop().getaddrinfo(
            host, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        # Nothing resolves, so there is nothing to protect: the fetch will fail
        # on its own, with a better error than anything guessed at here.
        return

    for info in resolved:
        try:
            address = ipaddress.ip_address(info[4][0].split("%")[0])
        except ValueError:
            continue
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            raise ApiError(
                403,
                "url_not_allowed",
                "That link points inside the server's own network.",
                host=host,
            )


# Enough for the http -> https and www hops a real file goes through, few enough
# that a redirect loop stops being our problem.
MAX_REDIRECTS = 5


async def download_media(
    client: httpx.AsyncClient,
    url: str,
    workspace: Path,
    max_bytes: int,
    *,
    allow_private: bool = False,
    on_progress: Callable[[int, int | None], Awaitable[None]] | None = None,
) -> Path:
    """Stream a direct link onto disk, the same way an upload is streamed.

    Counting bytes as they arrive rather than trusting Content-Length: the
    header is optional, and a server that lies about it would otherwise be
    allowed to fill the volume.

    Redirects are followed by hand because every hop has to pass the same host
    check as the original link -- httpx following them for us would turn a
    public redirector into a way through it.

    `on_progress` is told the bytes so far and the total the server claimed, if
    it claimed one. Whether that is worth showing anybody is not decided here.
    """
    suffix = PurePosixPath(unquote(urlparse(url).path)).suffix or ".bin"
    target = workspace / f"source{suffix}"
    workspace.mkdir(parents=True, exist_ok=True)

    written = 0
    current = url
    try:
        for _hop in range(MAX_REDIRECTS + 1):
            await ensure_allowed_host(current, allow_private=allow_private)

            async with client.stream("GET", current, follow_redirects=False) as response:
                location = response.headers.get("location")
                if response.is_redirect and location:
                    current = str(response.url.join(location))
                    continue

                if response.status_code >= 400:
                    raise ApiError(
                        502,
                        "download_failed",
                        f"The server answered {response.status_code} for that link.",
                        status=response.status_code,
                        url=url,
                    )
                declared = _content_length(response)
                with target.open("wb") as sink:
                    # Whatever arrives, when it arrives: buffering up to a fixed
                    # size before writing would also mean saying nothing about
                    # the download until that much of it had accumulated.
                    async for chunk in response.aiter_bytes():
                        written += len(chunk)
                        if on_progress is not None:
                            await on_progress(written, declared)
                        if written > max_bytes:
                            sink.close()
                            target.unlink(missing_ok=True)
                            raise ApiError(
                                413,
                                "download_too_large",
                                f"That file exceeds the {max_bytes} byte limit.",
                                max_bytes=max_bytes,
                            )
                        sink.write(chunk)
                break
        else:
            raise ApiError(
                502, "download_failed", "That link redirected too many times.", status=310, url=url
            )
    except httpx.HTTPError as failure:
        target.unlink(missing_ok=True)
        raise ApiError(
            502,
            "download_unreachable",
            "That link could not be reached.",
            url=url,
            detail=str(failure)[:200],
        ) from failure

    if written == 0:
        target.unlink(missing_ok=True)
        raise ApiError(502, "download_failed", "That link returned nothing.", status=204, url=url)

    return target


def _content_length(response: httpx.Response) -> int | None:
    """What the server says it is about to send, if anything believable.

    A header, not a promise: the byte count that decides anything is the one
    counted on arrival. This is only ever used to say how far along we are.
    """
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        declared = int(raw)
    except ValueError:
        return None
    return declared if declared > 0 else None


@dataclass(frozen=True)
class FetchedMedia:
    path: Path
    title: str | None = None
    author: str | None = None
    published_on: str | None = None
    thumbnail: Path | None = None


async def fetch_with_ytdlp(binary: str, url: str, workspace: Path, max_bytes: int) -> FetchedMedia:
    """Hand a page to yt-dlp and take back audio plus what it learned.

    Only the audio: pulling a 4K stream to throw away every frame of it costs
    bandwidth and disk for nothing. The metadata comes back through the info
    json rather than stdout, because a title may contain anything at all,
    including the newline that would break a line-oriented protocol.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    template = workspace / "source.%(ext)s"

    code, stdout, stderr = await run(
        binary,
        "--no-playlist",
        "--no-warnings",
        "--no-progress",
        "--no-continue",
        "-f", "bestaudio/best",
        "--max-filesize", str(max_bytes),
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "-o", str(template),
        "--print", "after_move:%(filepath)s",
        url,
    )
    report = f"{stderr.decode(errors='replace')}\n{stdout.decode(errors='replace')}".strip()

    if code != 0:
        raise ApiError(
            502,
            "ytdlp_failed",
            "yt-dlp could not fetch that link.",
            url=url,
            detail=report[-500:],
        )

    printed = [line for line in stdout.decode(errors="replace").splitlines() if line.strip()]
    media = Path(printed[-1].strip()) if printed else None
    if media is None or not media.is_file():
        # A file over the limit is not an error to yt-dlp: it skips the download,
        # says so, and exits successfully, leaving us with nothing to transcribe.
        if "max-filesize" in report.lower():
            raise ApiError(
                413,
                "download_too_large",
                f"That recording exceeds the {max_bytes} byte limit.",
                max_bytes=max_bytes,
            )
        raise ApiError(
            502,
            "ytdlp_failed",
            "yt-dlp downloaded nothing.",
            url=url,
            detail=report[-500:],
        )

    info_path = media.with_suffix(".info.json")
    info: dict[str, object] = {}
    if info_path.is_file():
        try:
            info = json.loads(info_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Metadata is a nicety. A recording with no title still transcribes.
            info = {}
        info_path.unlink(missing_ok=True)

    thumbnail = media.with_suffix(".jpg")
    return FetchedMedia(
        path=media,
        title=_text(info.get("title")),
        author=_text(info.get("uploader") or info.get("channel") or info.get("artist")),
        published_on=_iso_date(info.get("upload_date")),
        thumbnail=thumbnail if thumbnail.is_file() else None,
    )


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _iso_date(value: object) -> str | None:
    """yt-dlp reports YYYYMMDD. Anything else is not worth guessing at."""
    raw = _text(value)
    if raw is None or len(raw) != 8 or not raw.isdigit():
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
