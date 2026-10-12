"""BattleConfig: defaults, validation, derived Robocode rules, TOML round trip."""

import tomllib

import pytest

from terrabots.battle.config import BattleConfig, BattleConfigError, BattleFile


def test_defaults_are_valid() -> None:
    BattleConfig()


@pytest.mark.parametrize("field, value", [
    ("width", 8), ("rounds", 0), ("terrain", "lava"),
    ("hit_energy_return", "all"), ("max_velocity", -1), ("seed", 1.5),
])
def test_invalid_values_name_the_field(field: str, value: object) -> None:
    with pytest.raises(BattleConfigError, match=field):
        BattleConfig(**{field: value})


def test_unknown_setting_rejected() -> None:
    with pytest.raises(BattleConfigError, match="bulet_power"):
        BattleConfig.from_dict({"bulet_power": 3})


def test_min_power_above_max_rejected() -> None:
    with pytest.raises(BattleConfigError, match="min_bullet_power"):
        BattleConfig(min_bullet_power=2.0, max_bullet_power=1.0)


def test_robocode_damage_formula() -> None:
    cfg = BattleConfig()
    assert cfg.damage(1.0) == pytest.approx(4.0)
    assert cfg.damage(3.0) == pytest.approx(16.0)   # 4·3 + 2·(3-1)
    assert BattleConfig(max_damage=10).damage(3.0) == pytest.approx(10.0)
    assert BattleConfig(damage_formula="linear", damage_per_power=5).damage(2.0) == pytest.approx(10.0)


def test_energy_return_modes() -> None:
    assert BattleConfig(hit_energy_return="damage").energy_return(3.0, 16.0) == 16.0
    assert BattleConfig(hit_energy_return="robocode").energy_return(3.0, 16.0) == 9.0
    assert BattleConfig(hit_energy_return="none").energy_return(3.0, 16.0) == 0.0


def test_bullet_speed_scaled_from_pixels() -> None:
    cfg = BattleConfig()
    assert cfg.bullet_speed(3.0) == pytest.approx(11 / 16)  # 20 - 3·3 px/tick
    assert BattleConfig(max_bullet_speed=0.5).bullet_speed(0.1) == pytest.approx(0.5)
    assert BattleConfig(bullet_speed_fixed=1.0).bullet_speed(3.0) == pytest.approx(1.0)


def test_body_turn_slows_with_speed() -> None:
    cfg = BattleConfig()
    assert cfg.max_body_turn(0.0) == pytest.approx(10.0)
    assert cfg.max_body_turn(0.5) == pytest.approx(4.0)     # 10 - 0.75·8


def test_battle_file_toml_round_trip() -> None:
    bf = BattleFile.from_dict({"rounds": 3, "seed": 7,
                               "bots": [{"spec": "a.b:C", "count": 2}]})
    again = BattleFile.from_dict(tomllib.loads(bf.to_toml()))
    assert again == bf


def test_example_battle_file_loads() -> None:
    bf = BattleFile.load("battles/example.toml")
    assert bf.config.rounds == 5
    assert sum(b.count for b in bf.bots) == 6


def test_bad_bot_entry_rejected() -> None:
    with pytest.raises(BattleConfigError, match=r"bots\[0\]"):
        BattleFile.from_dict({"bots": [{"count": 2}]})
