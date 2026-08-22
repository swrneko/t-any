# tany

Self-hosted transcription. Feed it a file or a link, get timestamped text, and
optionally an LLM summary shaped by your own presets.

Everything AI-shaped happens over OpenAI-compatible HTTP, so you can point it at
Ollama, LM Studio, vLLM, a local Whisper server, or a cloud API — the service
itself ships no model weights.

> **Status: everything planned is built.** Upload a file or paste a link — a
> direct one, or a page from any of the ~1800 sites yt-dlp handles — and you get
> a transcript with timestamps, a player that follows it, and a summary shaped
> by whichever preset you pick. The archive is searchable, exports to
> txt/md/srt/vtt/json, and can be shared as a read-only link. A line the model
> misheard can be corrected in place, and recordings with more than one voice
> can be split by speaker. See [SPEC.md](SPEC.md) for why
> each part works the way it does.

## Quick start

```bash
cp .env.example .env      # optional; every value has a default
docker compose up -d
```

Open `http://localhost:8927`. The first visit asks you to create an
administrator account — there is no default password and no open registration.

To actually transcribe anything you need a speech-to-text endpoint. Any
OpenAI-compatible `/v1/audio/transcriptions` server works — [speaches],
whisper.cpp's server, faster-whisper-server, LocalAI, or the OpenAI API. Point
`STT_BASE_URL` at it in `.env`.

If that server runs on the host rather than in Docker, the address inside the
container is `http://host.docker.internal:PORT/v1`, not `localhost`. That single
mistake accounts for most self-hosting failures.

Summaries need a second endpoint, `LLM_BASE_URL`, pointing at anything that
speaks `/v1/chat/completions` — Ollama, LM Studio, vLLM, or a cloud API.
Transcription works without it; only summarising is unavailable.

Set `LLM_CONTEXT_TOKENS` to your model's real context window. It defaults low on
purpose: guessing too high is the dangerous direction, because Ollama truncates
an over-long prompt without complaining and returns a confident summary of the
first third of the recording.

[speaches]: https://github.com/speaches-ai/speaches

## Speakers

Telling voices apart is optional and off by default, because it is slower than
transcription and pointless for a lecture:

```bash
docker compose --profile diarize up -d --build
```

Then set `DIARIZER_URL=http://diarizer:9000` and restart. A checkbox appears
beside the upload box; tick it and the transcript comes back split by speaker,
with `SPEAKER_00` renameable to whoever that was — once, in one place, and every
export and share link follows.

The model is gated: accept the terms of `pyannote/speaker-diarization-3.1` once
on huggingface.co and put a read token in `HF_TOKEN`. The image is built locally
rather than pulled, and it is large — torch plus the weights is several
gigabytes, which is exactly why it is a profile rather than a default.

If you would rather not run that container, `DIARIZER_URL` can point at anything
that answers `POST /diarize` with `{"segments": [{"start", "end", "speaker"}]}`.

## Configuration

All settings are environment variables; see [.env.example](.env.example).

`AUTH_MODE` picks how identity works:

| Mode | Behaviour |
|---|---|
| `builtin` | Accounts live in this service. First start opens a setup wizard. |
| `proxy` | Identity comes from a reverse proxy header (Authelia, authentik). |
| `disabled` | No authentication. Only reasonable behind a trusted localhost. |

`ADMIN_USERS=alice,bob` names administrators regardless of what the database
says. Set it whenever `AUTH_MODE=proxy`: identities arriving from a proxy have
no admin flag, so without it nobody can edit providers or manage accounts. In
`builtin` mode it doubles as the way back in when the only password is lost.

## Data and backups

Everything lives in one volume: the SQLite database, the normalised audio, and
the instance secret. To back up, copy the volume:

```bash
docker compose stop
tar czf tany-backup.tgz -C /var/lib/docker/volumes/tany_data/_data .
docker compose start
```

## Security notes

Read these before exposing the service to the internet.

- **There is no built-in HTTPS.** Put it behind Caddy, Traefik, or nginx. The
  service honours `X-Forwarded-*` so share links get the right scheme and host.
- **The encryption key sits next to the data it encrypts** (`/data/secret.key`).
  Provider API keys are encrypted with it, which protects them if a database
  backup leaks — it does *not* protect them from anyone who can read the
  volume. That trade-off is deliberate: a self-hosted service that demands
  external key management before it starts is a service nobody starts.
- **`AUTH_MODE=disabled` means exactly that.** Anyone who can reach the port has
  full access, including your provider API keys.

## Development

See [AGENTS.md](AGENTS.md).

## License

MIT
