"""
VisibilityMgr and MovementResolver scenarios:

- A rock wall blocks line-of-sight between two creatures at ground level.
- Standing on stairs (raised elevation) restores line-of-sight over a shorter
  obstacle, at an energy cost proportional to the climb.
- Rock blocks by height only; range culling happens before any raycast.
"""

from terrabots.world_terrain import (
    Cell,
    CreatureMoveProfile,
    MovementResolver,
    TerrainType,
    VisibilityMgr,
    WorldGrid,
)

GROUND = CreatureMoveProfile(eye_height_offset=1.0)


def build_test_world() -> WorldGrid:
    """
    Layout (10 wide x 3 tall), y=1 is the row of interest:

        x:  0  1  2  3  4  5  6  7  8  9
        y=1 .  .  .  R  S  S  .  .  .  .      R = rock, elevation 3
                                               S = stairs, elevation 2 and 4

    Observer starts at (0,1), target at (9,1). Rock at (3,1) is tall enough to
    block sight at ground level (eye height 1.0).
    """
    world = WorldGrid(width=10, height=3)
    world.set(3, 1, Cell(terrain=TerrainType.ROCK, elevation=3.0))
    world.set(4, 1, Cell(terrain=TerrainType.STAIRS, elevation=2.0))
    world.set(5, 1, Cell(terrain=TerrainType.STAIRS, elevation=4.0))
    return world


def test_tall_rock_blocks_ground_level_sight() -> None:
    vis = VisibilityMgr(build_test_world())
    assert vis.has_line_of_sight((0, 1), (9, 1), GROUND) is False


def test_stairs_give_vantage_over_rock() -> None:
    vis = VisibilityMgr(build_test_world())
    assert vis.has_line_of_sight((5, 1), (9, 1), GROUND) is True


def test_climbing_costs_more_than_flat_move() -> None:
    # (4,1) -> (5,1) differs only in elevation (2.0 -> 4.0), isolating the climb penalty.
    movement = MovementResolver(build_test_world())
    assert movement.move_cost((4, 1), (5, 1), GROUND) > GROUND.base_move_cost


def test_rock_is_impassable() -> None:
    movement = MovementResolver(build_test_world())
    assert movement.can_pass(3, 1, GROUND) is False


def test_short_rock_does_not_block_sight() -> None:
    # Distinguishes elevation-only LOS from the old "rock always blocks" shortcut.
    world = WorldGrid(width=5, height=1)
    world.set(2, 0, Cell(terrain=TerrainType.ROCK, elevation=0.2))
    assert VisibilityMgr(world).has_line_of_sight((0, 0), (4, 0), GROUND) is True


def test_range_cull_rejects_far_pairs() -> None:
    # Flat world: without the range check this pair would be visible.
    vis = VisibilityMgr(WorldGrid(width=50, height=1))
    short_range = CreatureMoveProfile(max_perception_range=10.0)
    assert vis.has_line_of_sight((0, 0), (40, 0), short_range) is False


def test_climb_limit_blocks_steep_step() -> None:
    world = WorldGrid(width=3, height=1)
    world.set(1, 0, Cell(terrain=TerrainType.PLAIN, elevation=5.0))
    movement = MovementResolver(world)
    assert movement.can_pass(1, 0, GROUND, from_pos=(0, 0)) is False
    assert movement.can_pass(1, 0, GROUND) is True  # no from_pos: spawn placement
