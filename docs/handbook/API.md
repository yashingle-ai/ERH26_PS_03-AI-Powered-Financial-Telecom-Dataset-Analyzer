# API — 17 endpoints, verified

All paths, roles and response keys below were **enumerated from a running app**, not from the source.
Verified 31 Jul: 18/18 checks including the auth and error paths. Two endpoints were added on
3 Aug (`/v1/analyze/progress/{ds}`, and `/v1/datasets` gained `cached`) and are marked below;
the 18-check sweep has not been re-run since.

Base `/v1`, JWT bearer. `POST /v1/auth/token` and `/v1/auth/refresh` are public; **everything else
requires the `analyst` role**. Interactive docs at `:8000/docs`.

---

## Two things that will cost you twenty minutes

**`app.routes` shows only 6 entries.** FastAPI holds an included router as a single
`_IncludedRouter`, so the 17 `/v1` endpoints do not appear when you iterate `app.routes`. Enumerate
`backend.app.api.main.v1.routes` instead. A made-up path returns **404** while `/v1/datasets` returns
**401**, which is how you tell "not mounted" from "needs auth" — that check is what proved the router
was fine after the enumeration suggested otherwise.

**Four paths that do not exist**, and their real equivalents:

| you will try | reality |
|---|---|
| `/v1/health` | health is **public at `/health`**, no prefix |
| `/v1/timeline/{ds}` | no such route — the timeline is inside `POST /v1/analyze` |
| `/v1/correlations/{ds}` | hits are in `POST /v1/analyze` → `correlation_hits`, `correlation_hits_medium` |
| `/v1/rejects/{ds}` | **`GET /v1/data-quality/{ds}`** → `rejects`. This is how rule 2 gets checked, so know where it lives |

---

## The endpoints

| method | path | role | returns |
|---|---|---|---|
| `GET` | `/health` | public | liveness |
| `POST` | `/v1/auth/token` | public | `access_token` (form: `username`, `password`) |
| `POST` | `/v1/auth/refresh` | public | a new token |
| `GET` | `/v1/datasets` | analyst | `datasets`, **`cached`** (3 Aug — durable snapshots on disk) |
| `POST` | `/v1/analyze` | analyst | `dataset`, `window_minutes`, **`from_cache`**, `summary`, `top_risk`, `correlation_hits`, `correlation_hits_medium`, `money_flow_series`, `file_counts`. Body takes **`force`** (3 Aug) |
| `GET` | `/v1/analyze/progress/{ds}` | analyst | **new 3 Aug** — live stage / percent / ETA for an in-flight analyze |
| `GET` | `/v1/entities/{ds}` | analyst | `total`, `items` — risk rows, ranked by `detection.risk_rank` |
| `GET` | `/v1/events/{ds}` | analyst | `total`, `items` |
| `GET` | `/v1/graph/{ds}` | analyst | `nodes`, `edges` |
| `GET` | `/v1/data-quality/{ds}` | analyst | `balance_breaks`, `rejects`, `parsed_files` |
| `GET` | `/v1/rule-eligibility/{ds}` | analyst | `rules`, `rules_enabled`, `rules_disabled`, `rules_that_fired`, `rules_enabled_but_inert` |
| `GET` | `/v1/risk-heatmap/{ds}` | analyst | `matrix`, `columns`, `entities`, `entities_scored`, `entities_with_a_fired_rule`, `rules_evaluated`, `unit` |
| `GET` | `/v1/document-mentions/{ds}` | analyst | `total`, `items`, `documents_indexed`, `prose_only_documents`, `kinds` |
| `GET` | `/v1/suggestions/{ds}` | analyst | `total`, `items`, `threshold` |
| `POST` | `/v1/query/{ds}` | analyst | NL query — Gemini plan or offline fallback |
| `POST` | `/v1/report/{ds}` | analyst | streams PDF or DOCX; **bad `fmt` → 400** |
| `POST` | `/v1/upload/{ds}` | analyst | refuses `demo` and `smoke` |

Every `{ds}` endpoint takes `?window=` (default 10) and goes through `_analyze()`, which is
`lru_cache`d on `(dataset, window)` **and, since 3 Aug, backed by a durable snapshot on disk** — so
the first call to a real case costs 20–35 minutes and the rest are instant, including after a
restart. Warm it deliberately before demoing.

---

## The ones worth reading closely

### `POST /v1/analyze` — caching, and how to defeat it

Two layers, added 3 Aug (`401ac0d`):

| layer | lives in | cleared by |
|---|---|---|
| `lru_cache` on `_analyze_uncoordinated` | process memory | a restart, an upload, or `force` |
| **durable snapshot** — the pickled `Investigation` plus a SQLite index row | `data/analysis_cache/<ds>__w<N>.pkl` | an upload into that dataset, or `force` |

The snapshot is what makes a restart survivable: reloading `fir-65-2024` used to cost 11 minutes
and now costs milliseconds. It is written temp-file-then-rename, so a crash mid-write cannot leave a
half-pickle that later loads as a corrupt `Investigation`.

`force: true` deletes the snapshot for that `(dataset, window)` and re-runs the full pipeline.
**You need it after changing a profile, a threshold or any pipeline code** — otherwise the snapshot
is served indefinitely and the API confidently returns figures that predate your change. An upload
into a dataset clears its snapshots automatically for the same reason.

`from_cache` in the response says which happened. A 130 ms cache hit and a 49-minute run are
otherwise indistinguishable to a caller.

> Concurrency is unchanged: one lock per `(dataset, window)`, so simultaneous identical requests
> share a single run rather than starting two ~3.5 GB pipelines.

### `GET /v1/analyze/progress/{ds}?window=` — what a long run is doing

Added 3 Aug (`fb0b016`). The pipeline is synchronous and CPU-bound, so a real case leaves the caller
holding an open request for 11–49 minutes with no signal. This endpoint is polled by a *second*
request to report where the first one has got to.

```json
{ "status": "running", "stage": "correlate", "stage_label": "Correlating call / IP / transfers",
  "percent": 71.4, "elapsed_seconds": 402.1, "eta_seconds": 161.0,
  "done": 812, "total": 986, "message": "…", "stages": [ … ] }
```

`status` is `idle` (no job for that key), `running`, `done` or `error`. The nine stages and their
weights come back in `stages`, so a client should **render the server's list rather than hardcode
its own** — the two drift otherwise, and nothing tests that they agree. Progress is held in a
module-level dict keyed by `(dataset, window)`, guarded by a lock, and the pipeline stages report
into it through a `contextvar` bound by the API thread.

Two properties worth knowing before you build on it:

- **It is in-process.** A restart loses it, and it does not work across multiple workers.
- **Polls will hang, not fail, during heavy stages.** The pipeline holds the GIL, so the whole API
  is unresponsive while it parses. Treat a slow or failed poll as "no news", never as an error —
  progress is decoration and must never be able to fail the analyze itself.

When a durable snapshot is hit, `finish(from_cache=True)` reports `"Loaded from cache"` and the
run never enters the pipeline body at all.

### `GET /v1/events/{ds}` — FR-15

Four filters, all on this route as well as the DSL: `entity`, `location`, `min_amount` / `max_amount`,
`start` / `end`. `location` matches **tower location or cell id**, so this route and `/v1/query`
answer the same question rather than two similar ones.

### `GET /v1/rule-eligibility/{ds}` — why a zero is a zero

Per rule: `enabled`, `eligible`, `fired`, and a `note`. **`eligible` is the rule's structural
precondition**, not the entity count — that fallback read "9,996 eligible, 0 fired" and looked like a
broken detector when the truth was that six entities in 7,358 reach the required fan-in.

When `eligible` is 0 the note says why in words an investigator can use: *"no entity is seen both
receiving and sending, so forwarding cannot be observed — a one-hop view of the money trail."* That
sentence is the thing that stops `fired = 0` reading as "nothing suspicious here".

`rules_enabled_but_inert` is the count to watch: enabled, nothing eligible, nothing fired.

### `GET /v1/risk-heatmap/{ds}` — FR-18

Entities × typologies, cells are the fired rule's weight. Entities with **no** fired rule are excluded
rather than drawn as an empty row, because a blank row reads as "assessed and clean" when it means
"nothing fired". `rules_evaluated` comes back alongside so a caller can tell an empty matrix from a
missing one.

### `GET /v1/document-mentions/{ds}` — FR-15 over the paperwork

`?identifier=` matches **as a normalised identifier, not as a substring** — a substring search over a
16,000-character affidavit returns the document for any four-digit run it happens to contain. A phone
typed with spaces, with `+91`, or in Gujarati numerals finds the same document as its bare ASCII form.
`?kind=` filters by document class (`affidavit`, `chargesheet`, `panchnama`, `bank_reply`, …).

**These are pointers into the evidence, never identity claims.** A record carries no
`own_identifiers`, no `primary`, no `event_type` — the three things entity resolution consumes.
`asserted_layers` is the officer's own layering determination, attributed to the document, and never
an input to the `layering` typology.

### `POST /v1/report/{ds}`

`{"fmt": "pdf"|"docx", "window_minutes": 10}`. Six sections; 5 is the STR draft and 6 the detection
audit. A generator failure returns a **500 with a message**, not a bare stack — it reaches into
matplotlib and reportlab and that is not the analyst's fault.

### `POST /v1/query/{ds}` — rule 1

Gemini receives a **schema and a question, never rows**. Offline fallback when no key is set. If you
extend this, keep case data out of the prompt; that is the rule with the least visible failure mode.

---

## Auth

```bash
curl -s -X POST localhost:8000/v1/auth/token -d "username=admin&password=$PW" | jq -r .access_token
```

With `ERAKSHAK_ADMIN_PASSWORD` / `ERAKSHAK_ANALYST_PASSWORD` unset the API **generates a random
password per boot and logs it once** — `docker compose logs api | grep "generated a random"`. No
default credential ships in the image, deliberately. `ERAKSHAK_JWT_SECRET` unset means an **ephemeral**
secret: tokens die on restart, which is fine for dev and wrong for anything else.

Errors use one consistent schema. Audit logging records `analyze`, `persist`, `report` and `upload`
with the username and dataset.
