"""Battle mode: Robocode-style tanks on Terrabots terrain. See docs/arena-spec.md."""

from terrabots.battle.actions import BattleAction
from terrabots.battle.agent import BattleAgent
from terrabots.battle.config import BattleConfig, BattleFile, BotEntry
from terrabots.battle.events import (
    BotDeath,
    BulletHit,
    BulletMissed,
    HitBot,
    HitByBullet,
    HitWall,
    ScannedBot,
)
from terrabots.battle.observation import BattleObservation
from terrabots.battle.runner import BattleResults, BattleRunner

__all__ = [
    "BattleAction", "BattleAgent", "BattleConfig", "BattleFile", "BotEntry",
    "BattleObservation", "BattleResults", "BattleRunner",
    "BotDeath", "BulletHit", "BulletMissed", "HitBot", "HitByBullet", "HitWall", "ScannedBot",
]
