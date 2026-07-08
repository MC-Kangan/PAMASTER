# Phase 2 Task 2 Report

## What you implemented

- Added `LiveNotionClient` in `backend/src/pa_investing/notion/live.py` behind the existing `NotionClient` interface.
- Added Notion request serialization on `NotionPagePayload` so payloads can be converted into a live create-page request with:
  - parent database id
  - `Name` title property
  - `External ID` rich text property
  - rich text properties for mapped fields
  - paragraph body content
- Expanded `NotionSync` in `backend/src/pa_investing/notion/sync.py` with:
  - `build_daily_review_payload(result: DailyReviewResult) -> NotionPagePayload`
  - `sync_daily_review(result: DailyReviewResult) -> str`
- Kept the fake client path intact for tests and local sync verification.

## What you tested and test results

Focused verification run:

`cd backend && ./.venv/bin/pytest tests/unit/test_live_notion_client.py tests/unit/test_notion_sync.py -v`

Result: `4 passed`

Covered behaviors:

- Live Notion client posts to the Notion pages endpoint with the configured database id and auth/version headers.
- Live Notion client serializes title, mapped properties, external id, and body into the outgoing request.
- Signal sync still writes through `FakeNotionClient`.
- Daily review sync builds the expected payload fields and writes to the `Daily Review` database name via `FakeNotionClient`.

## TDD Evidence

1. Added failing tests first:
   - `backend/tests/unit/test_live_notion_client.py`
   - `backend/tests/unit/test_notion_sync.py`
   - `backend/tests/fixtures/notion_create_page_response.json`
2. Ran focused tests before implementation.
3. Verified red state:
   - `ModuleNotFoundError: No module named 'pa_investing.notion.live'`
4. Implemented the minimal production code to satisfy the tests.
5. Re-ran the same focused test command and verified green: `4 passed`.

## Files changed

- `backend/src/pa_investing/notion/live.py`
- `backend/src/pa_investing/notion/schemas.py`
- `backend/src/pa_investing/notion/sync.py`
- `backend/tests/unit/test_live_notion_client.py`
- `backend/tests/unit/test_notion_sync.py`
- `backend/tests/fixtures/notion_create_page_response.json`

## Self-review findings

- The fake Notion path remains available and unchanged in behavior for existing signal sync tests.
- The new live client stays behind the explicit `NotionClient` interface.
- The current live implementation stores `External ID` in the page payload, which supports later idempotent matching work without coupling sync construction to HTTP request code.
- The current test scope is intentionally focused; it validates request construction and database-aware sync payloads, not broader Notion API lifecycle handling.

## Any issues or concerns

- `LiveNotionClient.upsert_page` currently performs a create-page request and embeds `External ID` for future idempotent matching, but it does not yet query/update an existing Notion page with the same external id.
- The request serializer assumes a `Name` title property and rich-text-compatible destination properties in the target Notion databases.
