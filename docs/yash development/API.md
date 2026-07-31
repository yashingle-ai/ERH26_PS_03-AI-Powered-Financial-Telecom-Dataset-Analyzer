# API — 15 endpoints, verified

All paths, roles and response keys below were **enumerated from a running app**, not from the source.
Verified 31 Jul: 18/18 checks including the auth and error paths.

Base `/v1`, JWT bearer. `POST /v1/auth/token` and `/v1/auth/refresh` are public; **everything else
requires the `analyst` role**. Interactive docs at `:8000/docs`.

---

## Two things that will cost you twenty minutes

**`app.routes` shows only 6 entries.** FastAPI holds an included router as a single
`_IncludedRouter`, so the 15 `/v1` endpoints do not appear when you iterate `app.routes`. Enumerate
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
| `GET` | `/v1/datasets` | analyst | `datasets` |
| `POST` | `/v1/analyze` | analyst | `dataset`, `window_minutes`, `summary`, `top_risk`, `correlation_hits`, `correlation_hits_medium`, `money_flow_series`, `file_counts` |
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
`lru_cache`d on `(dataset, window)` — so the first call to a real case costs 20–35 minutes and the
rest are instant. Warm it deliberately before demoing.

---

## The ones worth reading closely

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
