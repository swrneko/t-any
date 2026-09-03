import html
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import select

from app.errors import ApiError
from app.models import Job, Share, utcnow


def mount_share_preview(app: FastAPI, dist_dir: Path | None) -> None:
    """Serve /s/{token} as the SPA with link-preview tags in the head.

    A share link is the one address in this application that gets pasted into
    a chat window, and a chat window reads meta tags rather than running the
    app. Thirty lines here instead of a server-rendering framework everywhere.
    """
    if dist_dir is None or not (dist_dir / "index.html").is_file():
        return

    index = dist_dir / "index.html"

    @app.get("/s/{token}", include_in_schema=False)
    async def share_preview(token: str, request: Request) -> HTMLResponse:
        page = index.read_text(encoding="utf-8")

        async with request.app.state.db.session_factory() as session:
            share = await session.get(Share, token)
            expired = share is not None and (
                share.expires_at is not None and share.expires_at <= utcnow()
            )
            job = (
                await session.scalar(select(Job).where(Job.id == share.job_id))
                if share is not None and not expired
                else None
            )

        if job is not None:
            # Nothing beyond the title and how long it runs: a preview is shown
            # by whatever the link was pasted into, to whoever can see it there.
            minutes = round((job.duration_sec or 0) / 60)
            tags = (
                f'<meta property="og:type" content="article">'
                f'<meta property="og:title" content="{html.escape(job.title, quote=True)}">'
                f'<meta property="og:description" content="Transcript, {minutes} min">'
                f'<meta name="twitter:card" content="summary">'
            )
            page = page.replace("</head>", f"{tags}</head>", 1)

        return HTMLResponse(page)


def mount_frontend(app: FastAPI, dist_dir: Path | None) -> None:
    """Serve the built SPA from the API process.

    Vite compiles to static files, so no second Node container is needed in
    production. In development the directory is absent and Vite serves the UI
    itself, proxying /api here.
    """
    if dist_dir is None or not (dist_dir / "index.html").is_file():
        return

    index = dist_dir / "index.html"

    @app.get("/{spa_path:path}", include_in_schema=False)
    async def serve_spa(spa_path: str) -> FileResponse:
        if spa_path.startswith("api/"):
            # Registered after the API routers, so this only catches unmatched
            # /api paths. They must stay JSON: a client parsing index.html as an
            # error response is a genuinely baffling bug report.
            raise ApiError(404, "not_found", "No such endpoint.")

        candidate = (dist_dir / spa_path).resolve()
        if spa_path and candidate.is_file() and candidate.is_relative_to(dist_dir.resolve()):
            return FileResponse(candidate)

        return FileResponse(index)
