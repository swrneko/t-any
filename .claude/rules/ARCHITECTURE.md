# Architecture

## Stack

- **Backend** — Python 3.14, FastAPI, SQLAlchemy 2.0 async, SQLite in WAL mode,
  Alembic, argon2 for passwords, Fernet for provider API keys.
- **Frontend** — Vite + React 19 + TypeScript, Tailwind v4 and shadcn/ui with a
  tweakcn theme, i18next (en/ru). Compiles to static files served by FastAPI
  itself.
- **Media** — ffmpeg. No ML library is installed anywhere in this repository;
  speech-to-text and summarisation are remote OpenAI-compatible services.
- **Packaging** — one Docker image, one `/data` volume, one compose file.

## Commands

| What | Where | Command |
|---|---|---|
| Tests | `backend/` | `uv run pytest` |
| API (dev) | `backend/` | `uv run uvicorn app.main:create_app --factory --reload --port 8927` |
| Worker (dev) | `backend/` | `uv run python -m app.worker` |
| UI (dev) | `frontend/` | `npm run dev` |
| Typecheck UI | `frontend/` | `npm run typecheck` |
| Image | root | `docker build -t tany:dev .` |
| Diariser | root | `docker compose --profile diarize up -d --build` |
| New migration | `backend/` | `DATA_DIR=/tmp/x uv run alembic revision -m "..." --autogenerate` |

Alembic needs `DATA_DIR` because it migrates whichever database the settings
point at; the app passes the URL programmatically, the CLI falls back to the
same settings. Migration files are renamed to `000N_slug.py` by hand to keep
them readable in order.

## Layout

```
.
├── .github/workflows/          ci.yml on every push; release.yml on a v* tag
├── Dockerfile                  multi-stage: node builds the SPA, python runs it
├── docker-compose.yml          published image; .dev.yml overrides with build
├── SPEC.md                     design decisions with rationale (Russian)
├── diarizer/                   the only image with an ML library; profile "diarize"
├── backend/
│   ├── app/
│   │   ├── main.py             app factory + lifespan (migrations, db, secret)
│   │   ├── config.py           Settings, unprefixed env vars
│   │   ├── db.py               engine, session factory, SQLite pragmas
│   │   ├── models.py           SQLAlchemy models
│   │   ├── schemas.py          shared pydantic models
│   │   ├── deps.py             session/settings/current-user dependencies
│   │   ├── errors.py           ApiError -> {"error": {code, message, params}}
│   │   ├── security.py         argon2 hashing
│   │   ├── sessions.py         signed httpOnly session cookies
│   │   ├── secrets.py          /data/secret.key
│   │   ├── static.py           SPA serving with an /api-safe catch-all
│   │   ├── migrator.py         alembic upgrade head, in-process
│   │   ├── crypto.py           Fernet encryption and masking for API keys
│   │   ├── seed.py             env -> database bootstrap for providers
│   │   ├── storage.py          streaming upload to disk with SHA-256
│   │   ├── sources.py          link -> file: httpx for media, yt-dlp for pages
│   │   ├── media.py            ffprobe and ffmpeg; the only media knowledge
│   │   ├── probe.py            asks an endpoint for /v1/models; the API's only
│   │   │                       outbound call
│   │   ├── retention.py        removing a recording, by hand or by policy
│   │   ├── webhooks.py         the stored address a finished job is announced to
│   │   ├── stt.py              OpenAI transcription protocol client
│   │   ├── languages.py        what a provider calls a language vs what it takes
│   │   ├── llm.py              OpenAI chat protocol client, plain and streamed
│   │   ├── diarize.py          the diariser's own protocol, and the overlap merge
│   │   ├── exports.py          txt/md/srt/vtt rendering, pure and on demand
│   │   ├── search.py           FTS5 query building and the snippet contract
│   │   ├── chunking.py         where to cut a long recording
│   │   ├── summarize.py        token budget and map-reduce splitting
│   │   ├── summary_runner.py   produces one summary, in one pass or in stages
│   │   ├── presets.py          the built-in prompts
│   │   ├── worker.py           claim loop; also the worker entrypoint
│   │   └── api/                health, setup, auth, jobs, providers, presets,
│   │                           summaries, search, tokens, users, settings
│   │                           (retention and disk usage), public (no session)
│   ├── migrations/             alembic
│   └── tests/                  pytest, async, real HTTP through ASGITransport
│       └── stubs.py            stand-in STT server (a stub, never a patch)
└── frontend/src/
    ├── api/client.ts           fetch wrapper, throws ApiError with a code
    ├── index.css               the whole theme: two oklch palettes, one import
    ├── i18n.ts + locales/      en, ru
    ├── useApiError.ts          error code -> translated message
    ├── lib/utils.ts            cn(), the only thing shadcn needs from us
    ├── lib/language.ts         a code from the API -> a name in the UI's language
    ├── useJobFeed.ts           one job feed above the router: queue vs archive
    ├── components/ui/          shadcn components, owned and editable
    ├── components/             AppShell, AuthLayout, Field, JobList, ExportMenu,
    │                           ShareDialog, Theme/LanguageSwitch
    └── pages/                  Setup, Login, Jobs (the queue), History (archive
                                and search), Transcript, Settings (a shell over
                                settings/*), Shared (no account needed)
```

## Invariants

1. **No ML in the backend.** STT, LLM and diarisation are three independent HTTP
   clients with three different protocols, never a shared "AI provider"
   abstraction. The one place in this repository that imports a model library
   is `diarizer/`, which is a separate image behind a compose profile because
   no OpenAI-compatible endpoint for diarisation exists to point at.
2. **Raw STT output is immutable.** Exports (txt/md/srt/vtt) and user edits are
   layers computed on top; changing an export format never re-transcribes.
3. **`owner_id` exists from the first migration.** Retrofitting it later would
   mean rewriting every query.
4. **The queue is the `jobs` table.** No broker. Claiming is a single
   `UPDATE ... RETURNING` transaction; stale heartbeats requeue on worker start.
5. **The API is the whole product surface.** Anything the UI can do is reachable
   with a bearer token -- with one exception, which proves the rule: a token
   cannot mint another token, or a leaked one would survive its own revocation.
6. **The UI names colours, never picks them.** Components use the semantic
   tokens (`bg-primary`, `text-muted-foreground`); the two oklch blocks in
   `index.css` are the only place a value is written, so replacing them
   replaces the theme. `--warning` and `--success` were added to that set
   because this app reports degraded configuration and finished work, which
   the shadcn defaults have no colour for.

7. **The queue and the archive are different questions.** The home page answers
   "what is happening now" and the history page answers "what do I have"; a job
   appears on the first until it is terminal, and stays there for the rest of
   the session so it does not vanish under the eye that is watching it. Two
   lists holding the same rows would leave neither of them meaning anything.

## Status

Milestone 7 (SPEC §13) is under way. Done: the navigation move -- three
screens, settings as a shell over addressed sections, search folded into the
archive; and providers, which are now written from the UI behind a real admin
gate (`ADMIN_USERS` names administrators whatever the database says, because
behind a proxy nothing else can), with one default per kind enforced by a
partial unique index and a connection test that reports what `/v1/models`
answered. And deletion: a recording can be removed whole, or reduced to its
words alone -- an hour of audio is tens of megabytes and the transcript of it
is tens of kilobytes, so freeing the first while keeping the second is the
operation that actually matters. Rows go before files, segments go explicitly
so the search index follows, and a recording still being worked on is refused
rather than pulled out from under the worker. Retention rides on top of that
same code: two policies, both off until a number is set, applied by the worker
on the hour beside its claim loop. And accounts, which `owner_id` had been
waiting for since the first migration: an administrator creates them, hands out
a password when somebody forgets theirs, and cannot leave the instance without
an administrator or delete somebody's recordings without being told how many
there are. Last, the API section: the webhook moved out of the environment into
the database, gained a test call so "did I type the address right" no longer
costs a whole transcription to answer, and sits beside a documentation block
that says the four things the generated schema cannot -- this instance's own
address, a curl that runs, where `/docs` is, and that errors are matched on
`code` rather than read as prose.

Milestone 7 is complete.

After it, two things the queue had been getting wrong. An upload can now be
several files at once: `POST /api/jobs` takes a repeated `file` part and makes
one recording out of all of them, joined in the order they were sent, so a
meeting that arrived split across cards produces one transcript with continuous
timestamps instead of three to stitch by hand. The home page asks which of the
two is meant -- one recording, or a pile that becomes either one recording or a
job each -- and the pile is a list you can reorder, because with everything
going into one file position is the only thing being chosen. Both outcomes are
visible afterwards: a joined recording carries a badge counting the files it
was made of, and a pile transcribed apart travels under one `batch_id` so the
archive shows it as the group it arrived in rather than as five adjacent rows
that look unrelated. The batch is named by the client, since the server sees
one upload at a time and could not tell they belong together. And a job's own
page now answers during the work as well as after it: uploading lands on it
directly, where the stage, the progress and the cancel button live until the
words replace them.

Beside it, the release path SPEC §10 promised and nothing implemented: `ci.yml`
runs the suite, the typecheck, the frontend build and a no-push image build on
every push and pull request; `release.yml` publishes `ghcr.io/<repo>` for amd64
and arm64 when a `v*` tag is pushed, which is what makes the `image:` line in
`docker-compose.yml` resolve to anything. `latest` follows tags rather than the
default branch, so a compose file pointing at it never picks up whatever landed
on main ten minutes ago.

All planned milestones (0 to 6) are complete: auth, the transcription pipeline, chunking on
silence, live progress over SSE, cancellation that really stops the work,
per-chunk retries, crash recovery, a player that follows the transcript,
summaries by preset with automatic map-reduce and a kept history, and ingest
from a link -- streamed directly when it points at a media file, handed to
yt-dlp when it points at a page, with the title, channel, date and cover the
extractor found. Then the archive: full-text search over every segment, export
to txt/md/srt/vtt/json with timestamps and speakers as options rather than as
formats, public read-only share links that preview themselves when pasted,
bearer tokens for scripts, and a webhook when a job finishes. A line the model
misheard can be corrected in place, beside the original rather than over it, and
the search index follows by trigger. Last, diarisation:
a container of its own, asked for per recording, merged onto the transcript by
overlap, with speakers renameable in one place.

Known gaps left deliberately open:

- The upload limit is per file, not per recording. Ten files just under it are
  accepted as one job, and the joined result is however large it turns out to
  be; the limit protects the request, and the sum has no request to protect.
- Joining decodes every part before it encodes anything, so a merged upload
  costs roughly what transcoding all of it costs, before a word is transcribed.
  The parts are held on disk until then, unlike a single upload which is
  converted and deleted immediately.
- A merged recording remembers its parts only as a list of names in
  `source_ref`. Which stretch of the transcript came from which file is not
  recorded, so a part cannot be replaced or re-run on its own.
- A batch is a label, not a thing. `batch_id` groups rows in the list and
  nothing else: there is no batch to open, to cancel, or to export, and one
  whose members are deleted down to one becomes an ordinary row again. The id
  comes from the browser, so two clients could in principle collide on one --
  they are UUIDs owned by one account, which makes that a theoretical worry.
- Diarisation runs after the whole recording is transcribed and reports no
  progress of its own -- the stage says what is happening and never says how
  far it has got. Streaming it would mean chunking two models against each
  other.
- Diarisation can be asked for again on a finished recording, and the words are
  not asked for again with it -- but the whole recording goes back to the
  diariser every time. There is no way to attribute one stretch of it, and a
  recording whose audio has been freed cannot be asked at all.
- Nothing checks that the diariser is reachable before a job is queued: the
  `has_diarizer` flag says a URL is configured, not that anything answers it.

- A retry reuses the map results a previous attempt got back, matched only by
  count. Correcting the transcript between two attempts leaves the earlier
  parts summarising the older wording; the reduce still sees them.
- The token estimate is characters divided by three, not a tokeniser. It is
  deliberately pessimistic, so it splits earlier than strictly necessary.

- Deletion is confirmed, never undone. There is no `deleted_at`, so nothing can
  be brought back; the alternative would put a filter in every query and leave
  files to sweep later, which is more machinery than a rare operation deserves.
- Retention is instance-wide, not per person. On an instance with two accounts
  one policy governs both archives, which is right for the size this is built
  for and wrong for any size above it.
- The sweeper measures age from `finished_at`, so a recording that never
  finished is never swept -- correct, but it means a failed job sits in the
  archive until somebody deletes it.
- The connection test asks `/v1/models`, which is part of the OpenAI surface
  but not universal: a server that does not implement it looks unreachable
  while working perfectly. The wording in the UI says so; nothing else can.
- The language table is whisper's own list of ninety-nine, so a provider that
  answers with something outside it -- a script subtag we do not split on, a
  language whisper never had -- is passed through verbatim rather than
  translated. Forcing an unknown string is what happened before the table
  existed, so nothing is worse for it, but nothing is better either.
- A correction is per line and has no history: the provider's words and the
  current correction, nothing between them. Who changed what, and when, is not
  recorded -- an instance with two people editing one transcript would want it.
- The webhook fires once and is never retried. A receiver that was down when a
  job finished has to poll the API to catch up; the test call proves the
  address, not that a real delivery will land.
- Search ranks by bm25 over segments, so a recording that says the word twice
  outranks nothing in particular. Grouping hits by job is done in the UI.
- A share link exposes the audio as well as the text. That is deliberate -- a
  transcript whose player cannot play is half a document -- but it means a
  leaked token leaks the recording too.
- A download counts bytes only when the server declares how many there will be,
  and yt-dlp reports nothing at all: its progress goes to a pipe nobody reads,
  and the printed filepath we do read arrives at the end. Both cases still name
  the stage, so the page says what is happening without saying how far along.
- ffmpeg has the same shape: it prints a running timestamp on stderr and the
  conversion stage ignores it. For audio it is seconds; for a two-hour video it
  is not.
- Which fetcher a link gets is decided by its extension alone. A media file
  served without one goes to yt-dlp, whose generic extractor usually copes.
- yt-dlp runs with no cookies and no proxy, so anything behind a login or a
  region lock fails with `ytdlp_failed` and nothing more specific.
- The private-address check is applied to every link and to every redirect hop
  we follow ourselves, but yt-dlp does its own fetching: a page on a public host
  that redirects it somewhere private is not covered. Sandboxing its network
  namespace is the real fix and is not done.
- Both SSE streams poll the database on a timer. That is fine at this size and
  survives multiple API processes, which a shared in-memory bus would not.
- The worker's healthcheck reports and nothing acts on it: compose marks the
  container unhealthy and leaves it running, because `restart:` does not watch
  health. Something outside has to be looking.
- Nothing tells the UI that no worker is running. The liveness file sits on the
  volume the API can read, but it is named after the worker's host, so the API
  would be guessing at names rather than asking a question -- and a queue that
  never moves is the most confusing failure this thing has.
