"""Walls: drives clockwise along the arena edges with its gun pointing inwards,
like Robocode's sample bot of the same name. Written with the Robocode-style
AdvancedRobot API, so it doubles as an example of that."""

from terrabots.battle.geometry import normalize_angle
from terrabots.battle.robocode import AdvancedRobot, ScannedRobotEvent

MARGIN = 2.2        # cells between the arena edge and the tank's centre


class Walls(AdvancedRobot):
    """Drives along the arena edges, gun pointing inwards; shoots what it sees."""

    def on_round_start(self, round_number, rounds):
        self.set_adjust_gun_for_robot_turn(True)
        self.set_adjust_radar_for_gun_turn(True)
        self.stuck = 0

    def tick(self):
        w, h, m = self.battle_field_width, self.battle_field_height, MARGIN + 0.5
        top, right = self.y >= h - m, self.x >= w - m
        bottom, left = self.y <= m, self.x <= m
        # Clockwise: along the top edge east, right edge south, bottom west, left north.
        if top and not right:
            course = 90
        elif right and not bottom:
            course = 180
        elif bottom and not left:
            course = 270
        elif left and not top:
            course = 0
        else:
            course = 0                       # not at an edge yet: head north to one
        if self.stuck > 2:                   # terrain in the way: try the next leg
            course += 90
        turn = normalize_angle(course - self.heading)
        self.set_turn_right(turn)
        self.set_ahead(5 if abs(turn) < 10 else 0.3)
        self.set_turn_gun_right(normalize_angle(course + 90 - self.gun_heading))   # inwards
        # Scan a narrow band around the gun, so what it sees is what it can hit.
        self.radar_side = -getattr(self, "radar_side", 1)
        offset = normalize_angle(self.radar_heading - self.gun_heading)
        self.set_turn_radar_right(-offset + 15 * self.radar_side)
        if self.velocity:
            self.stuck = 0

    def on_hit_wall(self, e):
        self.stuck += 1

    def on_scanned_robot(self, e: ScannedRobotEvent):
        if abs(normalize_angle(e.absolute_bearing - self.gun_heading)) < 6:
            self.set_fire(3 if e.distance < 10 else 2)
