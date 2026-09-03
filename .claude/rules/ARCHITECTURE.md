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
├── dev/stub.py                 STT + LLM + diariser, answered locally and free;
│                               a `stub` service in .dev.yml, no build of its own
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
    ├── index.css               the whole theme: two oklch palettes, the motion
    │                           and glass tokens, one import
    ├── i18n.ts + locales/      en, ru
    ├── useApiError.ts          error code -> translated message
    ├── lib/utils.ts            cn(), the only thing shadcn needs from us
    ├── lib/language.ts         a code from the API -> a name in the UI's language
    ├── lib/motion.ts           view transitions and the ripple's coordinates
    ├── lib/time.ts             a position in a recording, hours only if any
    ├── lib/paragraphs.ts       segments -> paragraphs, runs, and the find
    ├── lib/speakers.ts         a label -> one of six colours, held by name
    ├── useJobFeed.ts           one job feed above the router: queue vs archive
    ├── components/ui/          shadcn components, owned and editable
    ├── components/             AppShell (+ useBarSlot: a screen's own controls,
    │                           rendered into the bar's island),
    │                           ArchiveBar, AudioPlayer, AuthLayout,
    │                           Field, JobList, ExportMenu, MorphLink, Pager,
    │                           ShareDialog, Theme/LanguageSwitch,
    │                           TranscriptSearch, TranscriptTimeline
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

   There is now a second way to learn who spoke, and it is not a fourth client:
   `gpt-4o-transcribe-diarize` answers the transcription protocol with a format
   that carries speakers, so it is the STT client asking a different question
   rather than a diariser wearing its clothes. Which arrangement is in play is
   read off the model name (`stt.DIARIZING_MODELS`) -- a table rather than a
   probe, because `diarized_json` is a format one model accepts and every other
   endpoint rejects, so asking costs a failed job. Two consequences fall out of
   it. The recording is not chunked: those labels only mean anything inside one
   request, and two chunks come back with an "A" each who are not the same
   person -- so the model's cap on one request is a cap on the whole recording,
   and it is 1400 seconds. Twenty-three minutes, measured against the endpoint
   rather than read off a page: at 1500 seconds it says so in a sentence, and
   at 5000 it stops explaining and calls the file corrupt. That is short enough
   to rule this model out for a meeting, which is why the length is checked
   before a byte is uploaded and refused in those words.
   And the UI asks one question either way: `has_diarizer` answers "can this
   instance find speakers at all", by container or by model.
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
   the shadcn defaults have no colour for. `--speaker-1` to `--speaker-6` were
   added for the same reason and are hues rather than steps of one scale,
   because they answer "a different person" and not "further along" -- the chart
   set could not be borrowed, since in dark it is four blues and a teal. Six is
   the count, and they are written at the lightness a name has to be legible at,
   since one value paints both a block on the timeline and the name over a
   paragraph. The classes are spelled out in `lib/speakers.ts` rather than
   assembled, because Tailwind reads that file as text and `bg-speaker-${n}` is
   a class nobody generated. Glass is named the same way: a
   surface asks for `glass` or `glass-raised`, and how translucent that is, how
   far it blurs, what edge it carries and how it is lit are values written once
   beside the palettes. The lighting is a bevel from directly above -- a lit top
   edge, the light coming back up off the bottom one, the body's own shade under
   both -- written into the offsets rather than measured, because nothing here
   travels across the viewport and a measurement would return the same answer
   every frame. A control asks for `glass-control` instead, which is the same
   surface minus the return light: on a thirty-two pixel button that bounce
   lands against the hairline it is a pixel inside of, and two light lines a
   pixel apart are not thickness, they are a border drawn twice.

   `panel` is the other half of that and the more common one. Grouping is not
   floating: a region of a page that merely says "these things belong together"
   gets a tonal step and nothing else -- `--group`, one shade off the
   background, downward in light and upward in dark. No edge and no elevation,
   because an outline is a boundary worth defending and a shadow is a claim to
   be above the page. And a card inside a panel gives up its fill and its
   shadow and keeps its hairline (one unlayered rule on
   `[data-panel] [data-slot="card"]`, unlayered because a layered rule cannot
   outrank a utility) -- it is a division of the panel, not a second surface
   stacked on the first.

   **Nothing inside the page is frosted.** `--group` is an opaque colour and
   `main .glass` drops its blur for `--card`, which is what that glass resolves
   to over the background in either palette. This is not a preference, it is
   forced: an element at less than full opacity is its own backdrop root, so
   for the whole length of a screen's fade every frosted surface inside it has
   nothing behind it to sample and is not frosted. The blur can then only
   arrive in one step at the end -- discretely, never smoothly -- and that step
   is what reads as every block on the page flickering. Standing the surfaces
   in for themselves during the fade moves the step; it does not remove it. A
   colour is the same colour at every opacity, so the page fades as one piece.
   Nothing is lost: the blur was only ever hiding the ruled grid, and an opaque
   shade hides it perfectly. Glass is left to what floats above the page and
   never fades with it -- the bar, a menu, a dialog -- and those are all
   outside `main`, which is what the selector says.

   Fields were the hole in that and the plainest version of it: an input, a
   textarea and a select trigger asked for `bg-glass`, which is the fill
   without the surface -- no blur ever came with it -- so the grid ran straight
   through the middle of a control. Inside `main` they take `--card` at rest
   and `--muted` on focus, which is what the frosting would have resolved to
   and a step that exists in both palettes; on a white card there is no lighter
   left to go, so focus steps down rather than up.

7. **The UI names durations and curves, never picks them either.** Material's
   four easings and the duration buckets are `:root` variables outside both
   palettes, because how long a thing takes to move is not a question light and
   dark answer differently. A component writes `duration-(--motion-medium)
   ease-emphasized`, never `duration-300 ease-out`.

8. **Motion is decoration over a layout that already works.** Every transition
   is a view transition or a CSS animation, so a browser without
   `startViewTransition` and a person who asked for reduced motion both get the
   same state change with nothing animating it -- `lib/motion.ts` checks for
   both before it starts anything, and one media query flattens every duration
   in the stylesheet. No animation library is installed, and none is wanted:
   what is animated here is the browser's own before/after of a DOM change.

9. **One change, one animation.** A view transition renders the new state live
   inside its own snapshot, so anything the page would have animated by itself
   keeps animating in there, against the transition drawn over it -- the same
   movement described twice, on two clocks, which is what reads as a stutter.
   Three rules keep it to one. Entry animations are finished before the new
   state is captured (`settle()` in `lib/motion.ts`). Ordinary transitions are
   flattened for the length of the morph, so nothing eases underneath it. And a
   `view-transition-name` is declared for the one kind of change it is true of
   -- `data-morph="quiet"` beside it, taken away by the stylesheet for every
   other kind -- because a name left on permanently lifts its element out of the
   picture for the palette change and the list reorder as well, to cross-fade
   alone over both.

   **A screen change is not a view transition.** It was one, four times over:
   a cross-fade, then a fade-through in two halves, then the root held still
   with only a named page region fading. Every version was reported -- as the
   background flickering, as the inputs flickering, as the page changing shade
   and changing back, and finally as the page arriving squashed again. All of
   it is one thing. A view transition photographs the whole document, so the
   grid, the drifting light, the panels and every field are inside the picture
   and anything done to it is done to all of them at once, while whatever
   carries a name is captured apart and stands perfectly still -- that
   asymmetry is the flicker. Name the page region instead and its box is
   interpolated between two heights, which is the squashing, because an engine
   is free to stretch the picture into the box and `object-fit: none` did not
   stop Firefox doing it.

   So an ordinary navigation opens no transition at all. It is a plain
   navigation, and the arriving screen brings itself in with a CSS animation
   (`page-in`, keyed on the first segment of the address so React treats it as
   an arrival) -- opacity and twelve pixels of travel. The travel is not
   decoration: in the dark palette a panel is nine values out of 255 from the
   background it fades up from, so opacity alone is nine discrete steps held
   four frames each, and it was reported as exactly that. CSS has no dithering
   and there are no more levels to find; a moving edge is the only thing left
   that the eye can follow instead. There is no photograph, so there is no box, nothing to stretch,
   no frosted surface standing in for itself and no window in which the page on
   screen is not the page. The outgoing screen is not faded out -- it is simply
   gone -- so two screens are never both on the window and the doubling a
   cross-fade produces cannot happen. A settings section does the same one level
   in, and it is keyed on the section rather than on the address: `/settings`
   is a real render before it is a redirect -- the index route is a
   `<Navigate>` -- so an address key mounts the panel once empty, fades it in,
   and mounts it again a tick later with the section that was meant. Two blinks
   on every arrival, two more on every press of the gear. Resolved to a section,
   `/settings` and `/settings/users` are one key and one arrival.

   There is no exception, and there was one until it was looked at. A row
   opening its page kept a transition, on the reasoning that there really is one
   thing travelling: the row was named, the transcript's frame carried the same
   name, the box travelled between them. It is the same defect at its worst
   rather than a case the defect spares. A named box is interpolated between the
   height it had and the height it will have, and this box runs from a 69-pixel
   row to a 250-pixel page -- the largest such box in the app, so the picture
   stretched into it is stretched furthest. Reported, in the end, in exactly the
   words every earlier version was: it squashes like it used to. Opening a
   recording is now a plain navigation like every other.

   `quiet` is what is left for changes inside one screen that are not
   navigations at all -- a list reordering, a staged file leaving -- where the
   rows carry names and the rest of the document is told to swap outright.

   Two more things have to be true for any of it to hold. `BrowserRouter` is
   mounted with `useTransitions={false}`, because a
   navigation marked as a React transition is exactly what `flushSync` will not
   flush, and the browser would photograph "after" from a DOM still showing the
   old screen. And the element carrying a name has to survive the whole trip:
   the transcript page names the frame all its states share rather than the
   card inside it, since replacing a named element mid-flight makes the browser
   abandon the transition. `scrollbar-gutter: stable` belongs to the same
   family -- without it a short page and a long one have viewports of different
   widths, and the centred column arrives half a scrollbar away from where it
   left.

   Last, a name takes its element out of the surface it belongs to, and that
   is the price of travelling -- worth paying only when the surface is leaving
   anyway. The selected pill in the app bar and in the settings list used to
   travel from one item to the next, and both are lifted out of a surface that
   stays: for the length of the trip the item being walked to was missing from
   the list, because its picture was the one still in flight, and the item
   being left was missing from it as well. What the eye got was a background
   sliding between two blanks. Naming the highlight alone rather than the
   control is the same defect from the other side -- lifted, it is drawn over
   the picture it came out of, so the background arrived above the icon it is
   supposed to sit behind. Neither is the change that actually happened:
   two controls changed state where they stand, so they cross-fade where they
   stand, inside their surface's own picture, and nothing is named.

10. **Nothing that is read is resized.** A screen, a card or a row never
    arrives or leaves by scaling. At 99% every edge, every gap and every line
    of text is a percent off, and the real thing is on screen a moment later to
    be compared against, so it reads as the page turning up squashed and then
    unfolding -- not as depth. It was reported twice, on two different screens,
    as "the page shrinks and then goes back to normal", which is `scale(0.99)`
    described exactly. Entrances fade, and move only where the thing moving is
    smaller than the window: `rise` is translate plus opacity, a screen swap is
    not animated at all (see 9), and a drop zone with a file over it lights up
    rather than swelling. Scale is left to two cases --
    things too small to be read while they move (a switch thumb, a checkbox,
    the logo badge), and surfaces that grow out of nothing and so have no
    earlier size to be judged against (a menu, a dialog, a tooltip). A button
    is in neither: it carries a label, and pressing it to 97% and letting it
    grow back was the same complaint at the size of a control -- reported as
    the click feeling like lag rather than an answer. The press is answered by
    the ink alone, out fast and gone inside the control bucket, and a press
    whose ink is still spreading when the screen changes is finished by
    `settle()` along with everything else the transition supersedes.

    The browser can do it to us too, and did: the box around a captured screen
    animates between the height it had and the height it is going to have, and
    an engine that stretches the picture to fill that box draws the page short
    and lets it unfold. Firefox does, Chrome does not, which is why this one
    only ever reproduced in one browser. So it is forbidden rather than
    arranged around: `::view-transition-old(*)`/`new(*)` carry
    `object-fit: none` anchored top-left, which says the picture is never
    scaled whatever the box does, and let it overflow. Matching the box to the
    picture is not enough on its own -- the engine decides whether the picture
    obeys the box.

    There are no exceptions, and there used to be one. The container transform
    -- a row growing into the page it opens -- said `object-fit: cover` on
    purpose, on the reasoning that there the box *is* the shape being morphed.
    Cover magnified the row's photograph three and a half times on the way, and
    removing it only exposed the layer underneath: the box itself still ran from
    69 pixels to 250, and an engine that stretches a picture into its box drew
    the page squashed exactly as before. The trip is gone (see 9), and with it
    the last view transition opened on a navigation.

    The other half of that is to name only boxes that stay the same size when
    their contents are not what changed. A named box is interpolated between
    the height it had and the height it will have, and the page region is
    precisely the box whose height differs on every screen -- naming it is what
    "the page shrinks" was, every time it came back. It is not named now and
    the screen change is not a transition at all (see 9); the app bar keeps its
    name for the one transition that is left, and it is one size.

11. **The queue and the archive are different questions.** The home page answers
   "what is happening now" and the history page answers "what do I have"; a job
   appears on the first until it is terminal, and stays there for the rest of
   the session so it does not vanish under the eye that is watching it. Two
   lists holding the same rows would leave neither of them meaning anything.

12. **A transcript is read, not scrolled.** Eighty-four minutes came back as
   nine hundred and sixty-eight segments, and one segment is one breath -- the
   division is where the model stopped, not where anybody did. Stacked as nine
   hundred rows it is a log with no way into it, so four things are true of the
   page instead, and each of them answers a different question.

   The lines are gathered into paragraphs for reading and kept whole underneath.
   A new one starts when somebody else speaks, when the silence is long enough
   to hear, or when the running block reaches a length worth resting the eye at
   and a sentence ends -- with a hard cap for the speaker who never stops.
   Nothing is merged in the data: a click still seeks to the line under the
   cursor, a correction still belongs to one line, and a search hit still names
   one. `lib/paragraphs.ts` is the whole of that, and it is pure.

   The timeline is the only thing on the page that shows the recording rather
   than a window into it -- who talked, when, and where the real silences are --
   and it is the player's seek bar rather than a second bar under it. A line
   showing position and a map showing shape are one control asked two questions;
   drawn one above the other, with the same playhead on each, the position was
   simply stated twice. So `AudioPlayer` takes a `track` and keeps the button,
   the clock and the volume. The marker follows the element's own clock at one
   frame apiece and is written straight onto the node -- `timeupdate` arrives
   four times a second, which is a marker that hops, and re-rendering fifty
   blocks to move one of them would be paying for the wrong thing. Sharing a row
   with a clock has one more consequence:
   the elapsed time is written in the total's shape (`formatClock(at, length)`),
   since `0:00` growing into `1:23:30` is four characters appearing in a flex
   row: everything beside them moves, and a seek bar that is `flex-1` breathes
   in and out for the length of the recording. Tabular figures do not help when
   it is the count of them that changes.
   Runs, not segments: an hour and a half across six hundred
   pixels is eight seconds to the pixel, so every ordinary pause is sub-pixel
   and two hundred blocks each rounded up to something visible is a barcode
   rather than a conversation. Gaps narrower than the bar can draw are joined,
   which is what leaves a shape.

   Finding a word is the page's own, over a transcript already in the browser:
   it costs nothing, answers as it is typed, and counts corrections -- which the
   archive's index only learns about by trigger. It counts lines rather than
   occurrences, because "2 of 47" has to mean the same thing as the two arrows
   beside it.

   And all of it stays. Playing the recording, finding a word in it, seeing
   where you are and getting it off the page are the same kind of act, and on a
   page nine hundred lines long any of them scrolling away is a thing you have
   to scroll back for. So the player, the timeline, the find bar and the export
   controls are one element rendered in one of two places: under the title where
   they belong, and -- once the page has carried them up to the app bar --
   inside the bar's own island through `useBarSlot`, where they are the bar. One
   glass, one edge, one shadow. Sticking them to the bar's underside was the
   near miss: two surfaces a pixel apart are two surfaces however carefully they
   are aligned, and being one thing is not something alignment can achieve.

   The radius is the one the bar already had -- twenty-eight pixels, half the
   lifted bar's height, which is what made it a pill -- so the corners do not
   move when the surface grows; only how far down it reaches changes. The bar's
   own radius is not animated, because `9999px` to `28px` interpolates through
   shapes that all look the same and lands its one visible step at the end.

   Position is `sticky`'s job and not the observer's, and that division is what
   makes the move invisible. An observer answers at the end of a frame rather
   than during the scroll, so on a wheel that moves a hundred pixels at a time
   the panel had already sailed past the bar before anything was told, and
   arrived by jumping back down to it -- which is what "it attaches abruptly"
   was. Stuck at the bar's underside it parks on the browser's own clock, frame
   for frame, and by the time the observer speaks it is already standing where
   the bar will draw it: measured across the threshold, the top goes 100, 90,
   80, 70, 69 and never once backwards, and a three-hundred-pixel step hands
   over in one frame with one pixel of settle. The panel and the transcript
   share one tall box for this, tall being the point -- it is what the panel
   sticks inside -- and the mark is absolute, both so it costs no row and
   because a mark inside a stuck element would never move again.

   What is left for the move to do is the material, and what is smoothed is a
   joint rather than a journey: nothing travels, since the controls are already
   standing at the bar's underside when it happens. Two properties change and both interpolate
   -- the top corners close from twenty-eight to nothing, and the panel's own
   fill gives way to the bar's glass. `dock` and `undock` are animations and not
   transitions, because changing parent is a full unmount and nothing carries
   across that; they are applied only to a move, so a transcript opened straight
   onto a scrolled position does not play the docking as though it had just
   happened. Going out the fill is left alone: the bar has shrunk back to a pill
   by the first frame, and starting transparent there would show the page
   through the panel. The resting panel carries no shadow, and that is for the
   joint rather than for taste -- a five-layer glass shadow has no matching
   shape to interpolate towards, so it could only snap on and off.

   Three things have to be true for the move to be invisible. The audio element
   is mounted by the page and not by the controls (`Recording`), because
   changing parent is a full unmount and the browser would reload the file and
   start it again from zero, mid-sentence -- the controls hold nothing the
   element does not, so mounted elsewhere they read it and are correct at once.
   The header is `fixed` rather than sticky, so the bar growing by the controls'
   height cannot push the page down -- and it would have pushed the mark that
   decides when to dock down with it, back below the line, into a loop; `main`
   carries a constant clearance instead. And the room the controls had is held
   open while they are away, measured where they rest rather than where they
   land, since docked they are three pixels shorter and reserving that would
   pull the transcript up by three at the moment they left.

   Being in the bar settles the frosting question too: docked, the controls are
   outside `main` in the DOM, so `main :is(.glass, ...)` never sees them and
   they carry no `page-in` fade of their own -- which is the whole of the
   argument that nothing inside the page is frosted. At rest they are inside it
   and take the card's own opaque material, which is what that rule asks for.
   The whole thing fits in a hundred and thirty pixels only because the seek bar
   and the map are one control; two of them plus a row of buttons was half again
   as tall, which on a laptop is a quarter of the window spent on furniture.

   The seek bar's working area is a rectangle and the pill around it is a frame.
   A round end eats the first and last twelve pixels of a bar that tall, and
   those are the beginning and the end of the recording -- the two positions on
   it anybody can name. The dead margin either side is what curves, the marker
   is free to hang over it at both extremes, and the click arithmetic needs
   nothing said about any of it because it measures the element it is on, which
   is the rectangle.

   Following the audio is the fourth, and it is off the moment the reader takes
   over: a wheel or a scrolling key means "let me read somewhere else", and only
   the button turns it back on. It never scrolls while nothing is playing,
   because a page that moves under a stationary eye is worse than one that does
   not move at all. Nothing listens to `scroll` itself -- the page's own
   scrolling would switch it off on its first frame.

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

- The share page still lists one row per segment. Paragraphs, the timeline and
  the find bar are all on the owner's page only; a public link to an
  eighty-four-minute recording is still the wall of lines that page stopped
  being. `intoParagraphs` is pure and the shared payload carries the same
  segments and speakers, so this is a port rather than a design question.

- The archive's pages are cut in the browser. `GET /api/jobs` answers with the
  whole list and always did -- one feed above the router serves both screens,
  and the queue needs every pending job whatever page the archive is showing --
  so paging it on the server would mean a second endpoint and an SSE stream
  that no longer matches it. What the pager saves is laying out four hundred
  rows to read thirty, not bytes on the wire. At the size this is built for
  that is the right trade; an archive of tens of thousands would want the other
  one.

- The archive's filters are cut in the browser beside its pages, and for the
  same reason: the list is already there. Date and length are read off columns
  the API returns; the file type is not a column at all -- the backend keeps
  only what it extracted, so audio-or-video is guessed from the extension in
  `source_ref`, and a link that names no file is neither and shows only while
  the filter is off.

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
- A model that transcribes and diarises at once is used for the speakers and
  nothing else is asked of it: `known_speaker_names`/`known_speaker_references`
  are not sent, so the voices come back as "A" and "B" and are renamed by hand
  like the diariser's own labels. Handing it four reference clips would name
  them from the start, and there is no screen for collecting those clips.
- Asking that model for speakers after the fact transcribes the recording a
  second time. With a diariser of our own the transcript is read back and left
  alone; here the two halves are one request, so there is no half to ask for.
  It is done quietly rather than refused -- the alternative is a recording that
  can never have speakers on an installation with no container to run.
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
