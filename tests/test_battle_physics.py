"""Battle physics rules in isolation: kinematics, cell passability, radar arc, bullets."""

import pytest

from terrabots.battle.config import BattleConfig
from terrabots.battle.physics import (
    BattleBody,
    apply_turns,
    blocked_reason,
    boxes_overlap,
    footprint_passable,
    in_radar_arc,
    next_velocity,
    segment_box_t,
    segments_intersect_t,
    terrain_block_t,
)
from terrabots.world_terrain import Cell, CreatureMoveProfile, MovementResolver, TerrainType, WorldGrid

CFG = BattleConfig()
PROFILE = CreatureMoveProfile()


# --- velocity -------------------------------------------------------------

def test_accelerates_at_acceleration_rate() -> None:
    assert next_velocity(0.0, 0.5, CFG) == pytest.approx(CFG.acceleration)


def test_brakes_at_deceleration_rate() -> None:
    assert next_velocity(0.5, 0.0, CFG) == pytest.approx(0.5 - CFG.deceleration)


def test_reversing_brakes_first() -> None:
    assert next_velocity(0.3, -0.5, CFG) == pytest.approx(0.3 - CFG.deceleration)


def test_reversing_through_zero_uses_leftover_tick_to_accelerate() -> None:
    # 1 px/tick, braking 2 px/tick²: stops after half a tick, then accelerates
    # the other way for the remaining half at 1 px/tick² -> -0.5 px/tick.
    v = next_velocity(1 / 16, -0.5, CFG)
    assert v == pytest.approx(-0.5 / 16)


def test_velocity_clamped_to_max() -> None:
    v = 0.0
    for _ in range(50):
        v = next_velocity(v, 99.0, CFG)
    assert v == pytest.approx(CFG.max_velocity)


# --- turning --------------------------------------------------------------

def test_body_turn_limited_by_speed() -> None:
    body = BattleBody(0, 5, 5, velocity=0.5)
    apply_turns(body, 90, 0, 0, CFG, adjust_gun=False, adjust_radar=False)
    assert body.heading == pytest.approx(4.0)  # 10 - 0.75 * 8 px/tick


def test_gun_and_radar_carried_by_default() -> None:
    body = BattleBody(0, 5, 5)
    apply_turns(body, 10, 20, 45, CFG, adjust_gun=False, adjust_radar=False)
    assert body.gun_heading == pytest.approx(30.0)
    assert body.radar_heading == pytest.approx(75.0)
    assert body.radar_sweep == pytest.approx(75.0)


def test_adjust_flags_make_headings_independent() -> None:
    body = BattleBody(0, 5, 5)
    apply_turns(body, 10, 20, -45, CFG, adjust_gun=True, adjust_radar=True)
    assert (body.heading, body.gun_heading, body.radar_heading) == pytest.approx((10, 20, 315))


# --- passability ----------------------------------------------------------

HALF = CFG.body_half_width   # 1.125 cells: Robocode's 36 px square


def _ridge_world() -> WorldGrid:
    world = WorldGrid(20, 20)
    for y in range(20):
        world.set(10, y, Cell(TerrainType.PLAIN, elevation=5.0))   # too steep from 0
    world.set(14, 5, Cell(TerrainType.ROCK, elevation=1.0))
    return world


def test_arena_edge_blocks_the_whole_square() -> None:
    world = _ridge_world()
    mv = MovementResolver(world)
    assert blocked_reason(1.2, 5.5, 1.1, 5.5, world, mv, PROFILE, HALF) == "arena"
    assert blocked_reason(1.3, 5.5, 1.2, 5.5, world, mv, PROFILE, HALF) is None


def test_climb_limit_applies_when_a_corner_crosses_into_a_steep_cell() -> None:
    world = _ridge_world()
    mv = MovementResolver(world)
    # Centre at 8.8: right edge at 9.925, still in cell 9. Moving to 8.9 puts it in 10.
    assert blocked_reason(8.8, 5.5, 8.9, 5.5, world, mv, PROFILE, HALF) == "terrain"
    assert blocked_reason(8.7, 5.5, 8.8, 5.5, world, mv, PROFILE, HALF) is None


def test_rock_blocks_movement() -> None:
    world = _ridge_world()
    mv = MovementResolver(world)
    assert blocked_reason(12.8, 5.5, 12.9, 5.5, world, mv, PROFILE, HALF) == "terrain"


def test_spawn_needs_every_corner_passable() -> None:
    world = _ridge_world()
    mv = MovementResolver(world)
    assert not footprint_passable(14.5, 6.0, world, mv, PROFILE, HALF)   # covers the rock
    assert footprint_passable(17.0, 15.0, world, mv, PROFILE, HALF)


def test_boxes_overlap_is_axis_aligned() -> None:
    assert boxes_overlap(0, 0, 2.2, 2.2, HALF)       # corners overlap
    assert not boxes_overlap(0, 0, 2.3, 0, HALF)


# --- radar arc ------------------------------------------------------------

def _radar(prev: float, sweep: float) -> BattleBody:
    return BattleBody(0, 10, 10, radar_prev=prev, radar_sweep=sweep)


def test_target_inside_sweep_is_seen() -> None:
    assert in_radar_arc(_radar(0, 45), 15, 15, 0.45, 25)   # target at heading 45


def test_target_outside_sweep_is_not_seen() -> None:
    assert not in_radar_arc(_radar(0, 45), 15, 5, 0.45, 25)  # heading 135


def test_sweep_wraps_through_north() -> None:
    assert in_radar_arc(_radar(350, 20), 10.5, 15, 0.45, 25)  # heading ~5.7


def test_counter_clockwise_sweep() -> None:
    assert in_radar_arc(_radar(0, -45), 5, 15, 0.45, 25)      # heading 315


def test_unturned_radar_sees_bot_it_points_at() -> None:
    assert in_radar_arc(_radar(90, 0), 20, 10.2, 0.45, 25)


def test_out_of_radar_range() -> None:
    assert not in_radar_arc(_radar(80, 20), 40, 10, 0.45, 25)


# --- bullets --------------------------------------------------------------

def test_fast_bullet_cannot_skip_through_body() -> None:
    # Body sits between start and end of one tick's flight.
    assert segment_box_t(0, 0, 10, 0, 5, 0, HALF) == pytest.approx((5 - HALF) / 10)


def test_bullet_passing_beside_body_misses() -> None:
    assert segment_box_t(0, 0, 10, 0, 5, 1.2, HALF) is None


def test_bullet_hits_box_corner_a_circle_would_miss() -> None:
    # Diagonal pass near the corner: inside the square, outside its inscribed circle.
    assert segment_box_t(3.0, 1.0, 5.0, -1.0, 5, 0, HALF) is not None
    assert segment_box_t(3.0, 1.0, 5.0, -1.0, 5, 0, 0.45) is None


def test_crossing_bullets_intersect() -> None:
    assert segments_intersect_t((0, 0), (2, 2), (0, 2), (2, 0)) == pytest.approx(0.5)
    assert segments_intersect_t((0, 0), (1, 0), (0, 1), (1, 1)) is None
    # head-on along one line
    assert segments_intersect_t((0, 0), (1, 0), (1.5, 0), (0.5, 0)) == pytest.approx(0.5)
    assert segments_intersect_t((0, 0), (1, 0), (3, 0), (2, 0)) is None


def test_hill_above_flight_height_stops_bullet() -> None:
    world = WorldGrid(10, 3)
    world.set(5, 1, Cell(TerrainType.PLAIN, elevation=2.0))
    hit = terrain_block_t(4.5, 1.5, 6.5, 1.5, z=1.0, world=world)
    assert hit is not None and hit[1] == "terrain"
    assert terrain_block_t(4.5, 1.5, 6.5, 1.5, z=3.0, world=world) is None  # fired from high ground


def test_bullet_leaving_arena() -> None:
    world = WorldGrid(10, 3)
    hit = terrain_block_t(9.5, 1.5, 10.5, 1.5, z=1.0, world=world)
    assert hit is not None and hit[1] == "arena"
