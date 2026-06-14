# Tests (placeholder)

pytest + pytest-asyncio, with factory-boy + faker for fixtures.

Suggested layout (mirrors `app/` layers):

- `tests/conftest.py` — async db session, app client, factories
- `tests/factories/` — factory-boy model factories
- `tests/unit/` — services in isolation (SRS algorithm, state machine, generators)
- `tests/integration/` — repositories + routers against a test database
- `tests/e2e/` — capture -> exercise -> attempt -> SRS update flows
