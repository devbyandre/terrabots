"""
Demonstrates VisibilityMgr and MovementResolver against two concrete scenarios:

1. A rock wall blocks line-of-sight between two creatures at ground level.
2. Standing on stairs (raised elevation) restores line-of-sight over a shorter
   obstacle, at an energy cost proportional to the climb.

Run directly: python test_world_terrain.py
"""

from terrabots.world_terrain import (
    Cell,
    CreatureMoveProfile,
    MovementResolver,
    TerrainType,
    VisibilityMgr,
    WorldGrid,
)


def build_test_world() -> WorldGrid:
    """
    Layout (10 wide x 3 tall), y=1 is the row of interest:

        x:  0  1  2  3  4  5  6  7  8  9
        y=1 .  .  .  R  .  .  .  .  .  .      R = rock, elevation 3
                     S                         S = stairs at x=4..5, elevation 2

    Observer starts at (0,1), target at (9,1). Rock at (3,1) has elevation 3,
    tall enough to block sight at ground level (eye height ~1.0).
    """
    world = WorldGrid(width=10, height=3)

    # Rock obstacle: tall enough to block a ground-level observer.
    world.set(3, 1, Cell(terrain=TerrainType.ROCK, elevation=3.0))

    # Stairs leading up just before the rock, raising effective elevation.
    world.set(4, 1, Cell(terrain=TerrainType.STAIRS, elevation=2.0))
    world.set(5, 1, Cell(terrain=TerrainType.STAIRS, elevation=4.0))

    return world


def main() -> None:
    world = build_test_world()
    visibility = VisibilityMgr(world)
    movement = MovementResolver(world)

    ground_profile = CreatureMoveProfile(eye_height_offset=1.0)

    origin = (0, 1)
    target = (9, 1)

    # --- Scenario 1: ground-level sight is blocked by the rock ---
    blocked = visibility.has_line_of_sight(origin, target, ground_profile)
    print(f"[Scenario 1] Ground-level LOS from {origin} to {target}: "
          f"{'VISIBLE' if blocked else 'BLOCKED'} (expected: BLOCKED)")
    assert blocked is False, "Expected rock to block ground-level line of sight"

    # --- Scenario 2: observer climbs the stairs at (5,1), elevation 4.0 ---
    elevated_origin = (5, 1)
    from_stairs = visibility.has_line_of_sight(elevated_origin, target, ground_profile)
    print(f"[Scenario 2] Elevated LOS from {elevated_origin} to {target}: "
          f"{'VISIBLE' if from_stairs else 'BLOCKED'} (expected: VISIBLE)")
    assert from_stairs is True, "Expected elevated vantage to see over the rock"

    # --- Scenario 3: energy cost of climbing the stairs ---
    # (4,1) has elevation 2.0, (5,1) has elevation 4.0 -- moving between them is a
    # same-row step that only differs in elevation, isolating the climb penalty.
    cost_climb = movement.move_cost((4, 1), (5, 1), ground_profile)
    print(f"[Scenario 3] Energy cost climbing from elevation 2.0 to 4.0: {cost_climb:.2f} "
          f"(base {ground_profile.base_move_cost} + climb penalty)")
    assert cost_climb > ground_profile.base_move_cost, "Climbing should cost more than flat movement"

    # --- Scenario 4: rock is impassable regardless of wade/climb stats ---
    can_enter_rock = movement.can_pass(3, 1, ground_profile)
    print(f"[Scenario 4] Can creature enter rock cell (3,1)? {can_enter_rock} (expected: False)")
    assert can_enter_rock is False

    # --- Scenario 5: a SHORT rock no longer blocks sight (elevation-only rule) ---
    # This is the scenario that actually distinguishes the new behavior from the old
    # "rock always blocks" shortcut -- scenarios 1-2 use a rock tall enough (elevation
    # 3.0) that it would block either way, so they don't exercise this change.
    short_rock_world = WorldGrid(width=5, height=1)
    short_rock_world.set(2, 0, Cell(terrain=TerrainType.ROCK, elevation=0.2))
    short_rock_visibility = VisibilityMgr(short_rock_world)
    short_rock_origin = (0, 0)
    short_rock_target = (4, 0)
    sees_over_short_rock = short_rock_visibility.has_line_of_sight(
        short_rock_origin, short_rock_target, ground_profile
    )
    print(f"[Scenario 5] LOS over a short (0.2) rock at ground level: "
          f"{'VISIBLE' if sees_over_short_rock else 'BLOCKED'} (expected: VISIBLE)")
    assert sees_over_short_rock is True, (
        "Short rock should not block sight under elevation-only rules -- "
        "if this fails, the old 'rock always blocks' behavior may have regressed back in"
    )

    # --- Scenario 6: perception range cull rejects far pairs without raycasting ---
    # Flat, obstacle-free world -- if range weren't enforced, this would be VISIBLE.
    open_world = WorldGrid(width=50, height=1)
    open_visibility = VisibilityMgr(open_world)
    short_range_profile = CreatureMoveProfile(max_perception_range=10.0)
    far_origin, far_target = (0, 0), (40, 0)  # distance 40, well beyond range 10
    out_of_range = open_visibility.has_line_of_sight(far_origin, far_target, short_range_profile)
    print(f"[Scenario 6] LOS at distance 40 with max_perception_range=10: "
          f"{'VISIBLE' if out_of_range else 'BLOCKED'} (expected: BLOCKED, via range cull)")
    assert out_of_range is False, "Pair beyond max_perception_range should fail the cull"

    print("\nAll scenarios passed.")


if __name__ == "__main__":
    main()


def test_scenarios() -> None:
    """pytest entry point: runs every scenario; each asserts internally."""
    main()
