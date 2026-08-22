"""Ask an OpenAI-compatible endpoint whether it is there.

The one place the API process itself dials out. It answers a question the logs
would otherwise answer twenty minutes later, in the worker: most self-hosting
failures are `localhost` where `host.docker.internal` was meant, and finding
that out while typing the address beats finding it out from a failed job.

What it proves is narrow, and the wording in the UI says so: `/v1/models` is
part of the OpenAI surface but not every server implements it, so a refusal
here means "this endpoint did not answer that question", not "this will not
work".
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

# Short on purpose: this runs while somebody watches a spinner in a form.
PROBE_TIMEOUT = httpx.Timeout(10.0)

ClientFactory = Callable[[str, str | None], httpx.AsyncClient]


@dataclass(frozen=True)
class ProbeResult:
    reachable: bool
    status: int | None = None
    latency_ms: int | None = None
    models: list[str] = field(default_factory=list)
    error_code: str | None = None


def probe_client(base_url: str, api_key: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    return httpx.AsyncClient(base_url=base_url.rstrip("/"), headers=headers, timeout=PROBE_TIMEOUT)


async def probe_models(
    base_url: str, api_key: str | None, factory: ClientFactory = probe_client
) -> ProbeResult:
    started = time.monotonic()
    try:
        async with factory(base_url, api_key) as http:
            response = await http.get("/models")
    except httpx.RequestError:
        return ProbeResult(reachable=False, error_code="provider_unreachable")

    latency = round((time.monotonic() - started) * 1000)

    if response.status_code >= 400:
        # Reached, and unhappy -- usually a missing or wrong key. Worth telling
        # apart from silence, because the address is evidently right.
        return ProbeResult(
            reachable=False,
            status=response.status_code,
            latency_ms=latency,
            error_code="provider_rejected",
        )

    try:
        payload = response.json()
    except ValueError:
        return ProbeResult(
            reachable=True,
            status=response.status_code,
            latency_ms=latency,
            error_code="provider_not_openai",
        )

    data = payload.get("data") if isinstance(payload, dict) else None
    models = [
        entry["id"]
        for entry in (data or [])
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]
    return ProbeResult(
        reachable=True, status=response.status_code, latency_ms=latency, models=models
    )
