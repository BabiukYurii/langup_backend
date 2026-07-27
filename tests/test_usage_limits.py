from datetime import UTC, datetime

from test_exercises import StubGenerator, _seed_vocab

from app.enums.learning import ExerciseType
from app.enums.payments import SubscriptionStatus
from app.models import Plan, Subscription
from app.repositories.usage_limit import UsageLimitRepository
from app.schemas.exercise import ExercisePreferences
from app.services.learning.exercise_service import ExercisePoolService
from app.services.payments.usage_limit_service import METRIC_AI_GENERATIONS

_TODAY = datetime.now(UTC).strftime("%Y-%m-%d")


async def _service(session):
    return ExercisePoolService(session, StubGenerator())


async def test_free_generation_is_capped_per_day(session, monkeypatch):
    from app.core import settings

    monkeypatch.setattr(settings.limits, "FREE_DAILY_AI_GENERATIONS", 2)
    user_id = await _seed_vocab(session, "cap@x.com", ["alpha", "beta", "gamma", "delta"])
    service = await _service(session)
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FILL_IN_BLANKS]))

    created = await service.replenish(user_id)
    assert created == 2  # capped even though the pool target is higher

    row = await UsageLimitRepository(session).get(user_id, METRIC_AI_GENERATIONS, _TODAY)
    assert row.used == 2


async def test_free_second_refill_same_day_is_blocked(session, monkeypatch):
    from app.core import settings

    monkeypatch.setattr(settings.limits, "FREE_DAILY_AI_GENERATIONS", 2)
    user_id = await _seed_vocab(session, "cap2@x.com", ["alpha", "beta", "gamma", "delta"])
    service = await _service(session)
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FILL_IN_BLANKS]))

    await service.replenish(user_id)  # uses today's budget of 2
    # drain the pool so there is room to generate again
    for ex in (await service.exercises.get_many(user_id=user_id, limit=100))[0]:
        await service.exercises.update_one(ex, {"status": "COMPLETED"})

    assert await service.replenish(user_id) == 0  # budget spent for today


async def test_premium_is_unlimited(session, monkeypatch):
    from app.core import settings

    monkeypatch.setattr(settings.limits, "FREE_DAILY_AI_GENERATIONS", 2)
    user_id = await _seed_vocab(session, "premium@x.com", ["alpha", "beta", "gamma", "delta", "eps", "zeta"])
    plan = Plan(code="premium_monthly", tier="PREMIUM", interval="MONTHLY", price_cents=1999, currency="PLN")
    session.add(plan)
    await session.flush()
    session.add(Subscription(user_id=user_id, plan_uuid=plan.uuid, status=SubscriptionStatus.ACTIVE.value))
    await session.flush()

    service = await _service(session)
    await service.set_preferences(user_id, ExercisePreferences(exercise_types=[ExerciseType.FILL_IN_BLANKS]))

    created = await service.replenish(user_id)
    assert created == settings.exercises.EXERCISE_POOL_TARGET  # not capped
    # premium usage is not tracked
    assert await UsageLimitRepository(session).get(user_id, METRIC_AI_GENERATIONS, _TODAY) is None


async def test_quota_endpoint(app, client):
    from app.services.auth.oauth_google import get_google_verifier

    profile = {"sub": "q-1", "email": "quota@gmail.com", "email_verified": True, "name": "Q"}
    app.dependency_overrides[get_google_verifier] = lambda: lambda _t: profile
    token = (await client.post("/api/auth/google", json={"id_token": "x"})).json()["access_token"]
    resp = await client.get("/api/exercises/quota", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["unlimited"] is False
    assert body["remaining"] == body["limit"]  # nothing used yet
