from pydantic import Field

from app.core.config.base import BaseConfig


class LimitsConfig(BaseConfig):
    # Free tier: how many AI exercise generations a user gets per day. Premium
    # (active subscription) is unlimited. Reset is implicit — a new day is a new
    # counter row. 0 disables the limit entirely.
    FREE_DAILY_AI_GENERATIONS: int = Field(40, alias="FREE_DAILY_AI_GENERATIONS")
    # New accounts get a free Premium trial of this many days (0 disables).
    NEW_USER_TRIAL_DAYS: int = Field(30, alias="NEW_USER_TRIAL_DAYS")
    # Plan a granted trial points at (must exist in the plans table).
    TRIAL_PLAN_CODE: str = Field("premium_monthly", alias="TRIAL_PLAN_CODE")
