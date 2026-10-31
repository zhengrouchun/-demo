"""Platform-independent reward and tree rules from the GrowMate PRD."""
from datetime import date, timedelta
import math

SPECIES = [
    {"id": "apple", "name": "苹果树", "emoji": "🍎", "description": "从一颗种子开始，慢慢长大。"},
    {"id": "cherry", "name": "樱花树", "emoji": "🌸", "description": "连续完成三天专注后解锁。"},
    {"id": "orange", "name": "橘子树", "emoji": "🍊", "description": "完成一次至少六十分钟的专注后解锁。"},
]


def water_reward(seconds: int) -> int:
    minutes = seconds / 60
    if minutes < 10:
        return 0
    points = [(10, 2), (25, 6), (45, 12), (60, 18), (90, 30)]
    for (start, low), (end, high) in zip(points, points[1:]):
        if minutes <= end:
            return math.floor(low + (minutes - start) * (high - low) / (end - start))
    return math.floor(30 + (minutes - 90) * 0.4)


def growth_stage(growth: int) -> str:
    return next(label for threshold, label in [(500, "结果"), (300, "开花"), (150, "生长"), (60, "幼苗"), (20, "发芽"), (0, "种植")] if growth >= threshold)


def missing_water_days(last_watered: str, last_penalty: str | None, today: date) -> list[str]:
    """Only fully elapsed, new natural days count; today never counts."""
    start = date.fromisoformat(last_watered[:10]) + timedelta(days=1)
    if last_penalty:
        start = max(start, date.fromisoformat(last_penalty) + timedelta(days=1))
    days = []
    while start < today:
        days.append(start.isoformat())
        start += timedelta(days=1)
    return days


def has_three_day_streak(days: set[str]) -> bool:
    for day in days:
        current = date.fromisoformat(day)
        if all((current - timedelta(days=i)).isoformat() in days for i in (1, 2)):
            return True
    return False
