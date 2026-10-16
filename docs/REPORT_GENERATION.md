# AI-Powered Business Intelligence Report Generator

Generates a downloadable PDF analysis of the location selected on the dashboard map. The same flow runs from the dashboard's **Generate Detailed Report** button and from the chatbot ("Generate a comprehensive PDF report for this location.").

Every figure in the report is computed by the platform's existing engines, run on the server for the requested coordinates. Gemini only writes explanatory text, and that text is checked before use.

---

## Architecture

```text
Browser (static/js/report-generator.js)
  1. selected location  ← localStorage 'selectedLocation' (main.js)
  2. heatmap on screen  ← window.lastHeatmapAnalysis (set by main.js after /analyze-crowd-intensity/)
     re-run if it belongs to another location (> 30 m away)
  3. capture the Leaflet map onto a canvas (tiles + SVG overlays + markers + legend)
  4. POST /api/reports/generate/  (Supabase bearer token + CSRF token)
  5. poll GET /api/reports/<id>/status/
  6. GET /api/reports/<id>/download/ (bearer token) → Blob → file
        │
        ▼
report_generator (Django app)
  views.py            request validation, auth, ownership, download response
  validators.py       payload / screenshot / capture-location / AI-output checks
  services.py         admission (limits, duplicates, retention), background thread, stages
  data_collector.py   runs the existing analysis → snapshot
  ai_writer.py        5 Gemini stages → schema + number checks → fallback text
  content.py          deterministic text, business-specific roadmaps, risk register
  chart_generator.py  matplotlib charts from snapshot values
  flowchart_generator.py  inline-SVG flowcharts
  pdf_generator.py    Django template → WeasyPrint → PDF, then validation
  intent.py           chatbot report-request detection
templates/reports/    report.html + sections/*.html
```

### Reused analysis code (no duplicated business logic)

| Report section | Source |
|---|---|
| Heatmap sectors, thresholds, dominant intensity | `business_intelligence/analysis.py: classify_sectors` (also used by `/analyze-crowd-intensity/`) |
| ML recommendation, alternatives, dataset choices | `analysis.build_business_prediction` → `predict_business` (decision tree) |
| Go/No-Go feasibility | `analysis.evaluate_feasibility` (also used by `/check-feasibility/`) |
| Revenue, range, potential/confidence scores, risk | `business_intelligence/utils.calculate_smart_revenue` (Extended Huff engine) |
| Revenue breakdown (visitor proxy, market share, competition adjustment) | the engine's own layers (`FeatureExtractor`, `HuffModel`, `ExtendedHuffModel`) run with the same inputs; discarded unless they reproduce the engine's daily revenue exactly |
| Competitor list | `prediction_engine.huff_layer.is_competitor` (same rule the Huff layers use) |

To make this reuse possible, the sector and feasibility code that lived inline in `analyze_crowd_intensity` and `check_feasibility` was moved into `business_intelligence/analysis.py` unchanged. A randomised comparison of the old and new views (300 cases, both endpoints) produced identical JSON. `tracker.views.analyze_crowd_intensity`, which serves the URL, now delegates to the same view.

The feasibility rules use a narrower Overpass query (amenity/shop/tourism only). The report derives that input by filtering the main 2 km response to features with those keys, which is the same feature set. This avoids a second Overpass request.

---

## Report contents

Cover, contents, then:

1. **Executive summary**: KPI cards (each tagged Observed, Model or Estimate), summary, advantages, risks, scenarios, next steps, missing data.
2. **Location overview**: coordinates, radius, collection time, feature counts by category, a map of mapped features, flowchart A (analysis pipeline).
3. **Crowd heatmap analysis**: the live screenshot (or a labelled reconstruction), sector counts, sector chart and table, interpretation and limits.
4. **Business recommendations**: what the model is (72-row decision tree, label only), a candidate comparison with engine scores, feasibility per candidate, explanations, flowchart B.
5. **Competition and market**: matched competitors, distance chart, nearest places, and the engine's accessibility/demand indicators (labelled as proxies).
6. **Revenue forecast**: daily/monthly/annual gross sales, conservative/base/optimistic scenarios, a step-by-step breakdown, engine assumptions, flowchart D.
7. **Business feasibility**: the platform's Go/No-Go result with each rule shown as met or not met, what the check does not cover, and conditions to satisfy before investing.
8. **Implementation roadmap**: business-specific steps (objective, actions, evidence, outcome, risks), timeline chart (planning estimates), flowchart C.
9. **Risk analysis**: risk matrix and register. Ratings are either rule-based on platform data (the rule is printed) or qualitative judgement.
10. **Final recommendations**: ranked candidates, open questions, information to collect, action plan, flowchart E, investment checklist.

**Appendix:** report and data timestamps, sources, model assumptions, limitations, unavailable data.

### Data integrity rules

- **Provenance:** each figure is tagged *Observed* (map data), *Estimate* (model output), *AI text*, *Template text*, *Your input* or *Missing*.
- **Missing data:** a section without data prints "Data unavailable for this analysis." plus a reason. No values are substituted.
- **No footfall claims:** feature counts are never described as people.
- **Revenue:** figures are gross sales, and the report states that profit cannot be calculated.
- **Scenarios:** these are the engine's own `revenue_range` (±10–40% depending on its confidence score). They are not described as a statistical confidence interval.
- **Default assumptions:** business types without engine parameters (anything other than cafe, restaurant, fast_food, shop, supermarket or pharmacy) use generic defaults (₹600 spend, 5% conversion). The report flags this wherever it applies.
- **Proxy fields not shown:** the fields `calculate_smart_revenue` marks as mock proxies (`conversion_rate`, `customer_quality`, `dynamic_avg_spend`, `effective_customers`) are never presented as data.
- **Legacy footer revenue:** the map footer's "Est. Monthly Revenue" (a legacy formula) is identified as such and not mixed with the forecast.

---

## Heatmap screenshot capture

`captureMap()` in `static/js/report-generator.js` redraws the *live* Leaflet map onto a canvas at its on-screen positions (`getBoundingClientRect`):

1. Base tiles. The dashboard tile layer now uses `crossOrigin: true`; MapTiler sends `Access-Control-Allow-Origin: *`, so the tiles can be read back.
2. Leaflet's SVG overlay (heatmap circles, radius ring, route), serialised and drawn as an image.
3. Marker and shadow icons, re-requested with CORS (jsDelivr and cdnjs send CORS headers).
4. Legend and attribution.

The result is a JPEG data URL (quality 0.88, 0.7 if it is too large), up to 1,600 px wide.

**Integrity checks:**

- The browser records which location the on-screen heatmap was analysed for (`window.lastHeatmapAnalysis`). If that location is more than 30 m from the selected location, the heatmap is re-run first.
- The server rejects a screenshot whose analysed coordinates are more than 30 m from the requested location (HTTP 409 `heatmap_mismatch`).
- If the sector counts on screen differ from the server's re-analysis (OpenStreetMap changed in between), the PDF says so.
- If capture fails (blocked tiles, hidden map), the request is still sent with `capture_error`. The PDF shows a red warning and a server-drawn **reconstruction** captioned "not a screenshot". An illustrative image is never presented as the real map.

**Server-side screenshot validation:** PNG/JPEG only, at most `REPORT_SCREENSHOT_MAX_BYTES` (2 MB), 300×200 to 4096×4096 px, verified and re-encoded to PNG with Pillow (removing metadata and appended payloads), and deleted once the PDF is built.

---

## Gemini integration

The integration reuses `tracker.ai.gemini_service._get_gemini_config` (`GEMINI_API_KEY`, `GEMINI_MODEL_NAME`) and `sanitize_context_for_ai`. Five stages run in parallel, each asking for JSON (`response_mime_type: application/json`):

1. location summary
2. heatmap and recommendations
3. revenue
4. business-specific roadmap
5. executive summary and final recommendations

Each response is:

- validated against a schema (`prompts.STAGE_SCHEMAS`): types, lengths and required keys
- checked for figures: any number ≥ 10 (or any ₹/%/lakh/crore amount in the roadmap) that does not match an evidence value within rounding tolerance rejects the stage
- filtered to the real candidate business names

A stage that fails for any reason (no key, timeout, quota, invalid JSON, ungrounded figure) uses the deterministic text from `content.py`. The PDF labels each section as *AI text* or *Template text*, and the cover and appendix state whether AI commentary was used, partly used or unavailable. User-typed text (location and business names) goes into the prompt only inside the evidence JSON, and the system prompt tells the model to treat it as data.

---

## API

All endpoints require `Authorization: Bearer <Supabase access token>`. The token is verified with Supabase Auth (`/auth/v1/user`), and the verified user id is cached for 60 s under a SHA-256 hash of the token.

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/reports/generate/` | Start a report. Also needs `X-CSRFToken`. Returns **202** with `report_id` and stages. **400** invalid input (`no_location`, `invalid_radius`, `invalid_image`, …), **401** not signed in, **403** CSRF failure, **409** `heatmap_mismatch` or `busy` (with the running `report_id`), **413** screenshot too large, **429** rate limit / service busy. |
| GET | `/api/reports/<uuid>/status/` | `status` (`queued`/`running`/`succeeded`/`failed`), `stages` (`done`/`active`/`pending`/`failed`/`skipped`), `error`, `download_url`, `page_count`. |
| GET | `/api/reports/<uuid>/download/` | `application/pdf` attachment, `Cache-Control: no-store`. **409** if not ready. |

Request body for `generate`:

```json
{
  "location": {"name": "Indiranagar, Bengaluru", "latitude": 12.9784, "longitude": 77.6408},
  "radius_m": 2000,
  "business_type": "cafe",
  "scope": "full",
  "source": "dashboard",
  "heatmap": {
    "image": "data:image/jpeg;base64,...",
    "analysed_lat": 12.9784, "analysed_lon": 77.6408,
    "center_lat": 12.979, "center_lon": 77.641, "zoom": 14,
    "sector_counts": {"high": 9, "medium": 0, "low": 0},
    "captured_at": 1792200000000
  }
}
```

`radius_m` must be 2000, the radius the heatmap is computed for. Revenue, scores, feasibility and ownership are never accepted from the client.

---

## Security and privacy

- **Ownership:** reports are owned by the Supabase user id and always looked up by `(id, owner_id)`. Another user's id returns 404, the same as a missing one.
- **Unguessable ids:** report ids are UUID4, and the route only accepts UUIDs, so ids cannot be used for path traversal.
- **No user-influenced paths:** PDF bytes are stored in the database row.
- **CSRF:** enforced on `generate` in addition to the bearer token.
- **Abuse limits:** one active report per user (duplicates return the running job), `REPORT_MAX_PER_HOUR` per user, and `REPORT_MAX_CONCURRENT` across the server.
- **Retention:** reports expire after `REPORT_RETENTION_HOURS` (24 by default). Expired rows are purged on each new request and by `python manage.py cleanup_reports` (run it from cron in production). Jobs stuck for more than 10 minutes (for example after a restart) are marked failed.
- **No external fetches by the renderer:** the WeasyPrint URL fetcher only allows `data:` URIs and the bundled DejaVu font files. Report text cannot make the renderer fetch anything.
- **No sensitive data in the PDF:** the PDF contains no tokens, keys, e-mail addresses or session data. The filename is `business-report-YYYYMMDD-HHMM.pdf`, with no location in it.
- **Error responses:** internal exceptions are logged, and users see short messages without tracebacks.

---

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` / `GEMINI_MODEL_NAME` | – / `gemini-2.5-flash` | Existing Gemini settings, reused. Without a key, reports use template text. |
| `REPORT_AI_ENABLED` | `True` | Set `False` to skip Gemini entirely. |
| `REPORT_AI_TIMEOUT` | `25` | Seconds per Gemini stage. |
| `REPORT_RETENTION_HOURS` | `24` | How long PDFs are kept. |
| `REPORT_MAX_PER_HOUR` | `10` | Reports per user per hour. |
| `REPORT_MAX_CONCURRENT` | `2` | Reports generated at once on one server. |
| `REPORT_SCREENSHOT_MAX_BYTES` | `2097152` | Maximum decoded screenshot size. |
| `REPORT_RUN_INLINE` | `False` | Generate inside the request (tests only). |

### Dependencies

- **Python:** `weasyprint>=63`, `pypdf>=5`, `pillow` (in `requirements.txt`).
- **System:** WeasyPrint needs **Pango**:
  - macOS: `brew install pango`
  - Debian/Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fontconfig` (already added to the `Dockerfile`)
- **Design:** editorial layout on warm ivory pages, with the cover, Feasibility and Final recommendations on deep-navy pages and the Executive summary on a royal-blue page (palette in `report_generator/theme.py`, shared by the stylesheet, charts and flowcharts; page colours are CSS named pages in `templates/reports/report.html`). Charts and flowcharts are drawn on ivory, so they read as cards on dark pages. Fonts are bundled in `report_generator/fonts/` (SIL OFL): **Fraunces** for headings and italic statements, **DM Sans** for body text, and **DM Mono** for small uppercase labels, tags, table headers and page metadata. DM Sans and Fraunces include the ₹ glyph; DejaVu Sans (bundled with matplotlib) covers remaining symbols such as ☐. No system fonts are needed.
- **Frontend tests:** `npm install` (jsdom dev dependency), then `npm run test:js`.

---

## Deployment notes

- **Background work:** generation runs in a daemon thread inside the Daphne process, with no Celery or Redis. A typical report takes 5–60 s, mostly the Overpass request; rendering takes about 2 s. The browser polls, so HTTP timeouts don't apply.
- **Restarts:** a restart loses in-flight jobs. They are marked failed after 10 minutes, and the user can retry.
- **Storage:** reports live in the configured database (`db.sqlite3` by default). On Render the filesystem is ephemeral, so reports are lost on redeploy. That is acceptable for 24-hour downloads; persist them with a managed database if longer retention is needed.
- **Migrations:** the `Dockerfile` now runs `python manage.py migrate` at start-up. The SQLite file is not in the image, so this creates the report table, and the existing app tables that were previously never created there.
- **Memory:** about 100–200 MB peak per concurrent report. Matplotlib, WeasyPrint and Overpass responses of up to about 30k features dominate. Keep `REPORT_MAX_CONCURRENT` low on small instances.

---

## Testing

```bash
python manage.py test report_generator   # report tests (Overpass, Supabase and Gemini are mocked)
python manage.py test                    # whole suite
npm install && npm run test:js           # frontend tests (jsdom)
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| PDF says "The live heatmap screenshot is not available" | Capture failed; the reason is printed in the warning. Common causes: the map was hidden or too small, or a tile server without CORS headers. The report still uses the server's analysis and a labelled reconstruction. |
| `heatmap_mismatch` (409) | The heatmap on screen was for another place. The frontend retries once without the screenshot; re-run the heatmap for the selected location. |
| "AI-generated commentary was unavailable" | `GEMINI_API_KEY` missing, quota/timeout, or the AI output failed validation (the server log names the stage). The report is complete with template text. |
| "The PDF could not be created. A system dependency (WeasyPrint/Pango) is missing." | Install Pango (see Dependencies). `python -c "import weasyprint"` reproduces the error. |
| "OpenStreetMap data could not be retrieved" | All Overpass mirrors failed or timed out (they are public and rate-limited). Retry in a minute. |
| Download returns 401 | The Supabase session expired; sign in again. Downloads need the bearer token, so plain links do not work. |
| Download returns 404 | Wrong account, or the report expired (24 h) and was purged. |
| 429 | The per-user hourly limit or the server-wide concurrency limit was reached. |

---

## Known limitations

- **Data:** the platform has no footfall, rent, cost, income or sales data, so profit, break-even and market size are not estimated.
- **Coverage and radius:** OpenStreetMap coverage varies, and the report radius is fixed at the heatmap's 2 km.
- **Dense cities:** in densely mapped areas all 9 sectors are often "High", because buildings and roads are counted. The report explains this.
- **ML model:** 72 training rows, one label and no score; its suggestions (for example "ATM") can be poor matches.
- **Competitor matching:** matching by category name misses differently tagged places. For example, "Auto Repair Shop" does not match OSM `car_repair`, and the report warns when no competitors match.
- **Chatbot sectors:** the chatbot's own context builder (`tracker/ai/orchestrator.py`) uses a different 0.01° grid for its sector counts, and falls back to fixed numbers when the analysis fails. Reports never use that path, but chatbot answers can differ from the report.
- **Alternative locations:** AI relocation zones (`/api/generate-best-locations/`, 8 km query) are not included, because that query is too heavy to run reliably inside report generation.
