"""Cost guard — track daily token spend and block when over budget."""
import time

from fastapi import HTTPException

from app.config import settings

_daily_cost: float = 0.0
_cost_reset_day: str = time.strftime("%Y-%m-%d")

# GPT-4o-mini pricing (approximate)
_INPUT_COST_PER_1K = 0.00015
_OUTPUT_COST_PER_1K = 0.0006


def check_and_record_cost(input_tokens: int, output_tokens: int) -> None:
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today
    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail=f"Daily budget of ${settings.daily_budget_usd} exhausted. Try tomorrow.",
        )
    cost = (input_tokens / 1000) * _INPUT_COST_PER_1K + (output_tokens / 1000) * _OUTPUT_COST_PER_1K
    _daily_cost += cost


def get_daily_cost() -> float:
    return _daily_cost
