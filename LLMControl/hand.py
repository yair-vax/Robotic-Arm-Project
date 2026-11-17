"""Hardware layer for one AmazingHand (right hand, servo IDs 1-8).

Every motion goes through Hand.move_finger(), which clamps angles and speed
so that nothing the LLM asks for can push a servo out of its safe range.
"""

import time

import numpy as np

# ---------------------------------------------------------------------------
# Settings - edit these for your hand
# ---------------------------------------------------------------------------

SERIAL_PORT = "COM3"
BAUDRATE = 1000000

# Middle (calibration) position of each servo, in degrees, in servo-ID order 1..8.
# Replace with your own results from AmazingHand_Hand_FingerMiddlePos.py.
MIDDLE_POS = [3, 0, -5, -8, -2, 5, -12, 0]

# finger name -> (servo ID 1, servo ID 2)
FINGER_SERVOS = {
    "index": (1, 2),
    "middle": (3, 4),
    "ring": (5, 6),
    "thumb": (7, 8),
}
FINGERS = list(FINGER_SERVOS)

MAX_SPEED = 7
CLOSE_SPEED = 3

# Safety limits
ANGLE_LIMIT = 90.0      # each servo stays within +/- this many degrees of its middle
TILT_LIMIT = 30.0       # side-to-side tilt allowed through set_finger()
FLEX_OPEN = -35.0       # flex angle at bend 0%   (matches OpenHand in the demo)
FLEX_CLOSED = 90.0      # flex angle at bend 100% (matches CloseHand in the demo)


def _clamp(value, low, high):
    return max(low, min(high, value))


class DryRunController:
    """Stands in for the servo bus: prints commands instead of sending them."""

    def write_torque_enable(self, servo_id, value):
        print(f"    [dry-run] torque servo {servo_id} -> {value}")

    def write_goal_speed(self, servo_id, speed):
        pass  # printed together with the position by Hand.move_finger

    def write_goal_position(self, servo_id, position_rad):
        pass


class Hand:
    def __init__(self, port=SERIAL_PORT, dry_run=False):
        self.dry_run = dry_run
        if dry_run:
            self.c = DryRunController()
        else:
            from rustypot import Scs0009PyController

            self.c = Scs0009PyController(serial_port=port, baudrate=BAUDRATE, timeout=0.5)

        # Turn torque on for every servo (the original demos only enabled ID 1).
        for ids in FINGER_SERVOS.values():
            for servo_id in ids:
                self.c.write_torque_enable(servo_id, 1)  # 1 = On / 2 = Off / 3 = Free
                time.sleep(0.002)

    # -- low level ----------------------------------------------------------

    def move_finger(self, finger, angle_1, angle_2, speed=MAX_SPEED):
        """Send raw angles (degrees, relative to the middle position) to one finger."""
        if finger not in FINGER_SERVOS:
            raise ValueError(f"Unknown finger '{finger}'. Valid: {', '.join(FINGERS)}")

        angle_1 = _clamp(float(angle_1), -ANGLE_LIMIT, ANGLE_LIMIT)
        angle_2 = _clamp(float(angle_2), -ANGLE_LIMIT, ANGLE_LIMIT)
        speed = int(_clamp(int(speed), 1, MAX_SPEED))
        id_1, id_2 = FINGER_SERVOS[finger]

        if self.dry_run:
            print(f"    [dry-run] {finger:<6} servo {id_1}: {angle_1:6.1f} deg   "
                  f"servo {id_2}: {angle_2:6.1f} deg   speed {speed}")

        self.c.write_goal_speed(id_1, speed)
        time.sleep(0.0002)
        self.c.write_goal_speed(id_2, speed)
        time.sleep(0.0002)
        self.c.write_goal_position(id_1, np.deg2rad(MIDDLE_POS[id_1 - 1] + angle_1))
        self.c.write_goal_position(id_2, np.deg2rad(MIDDLE_POS[id_2 - 1] + angle_2))
        time.sleep(0.005)

    # -- friendly control used by the LLM ------------------------------------

    def set_finger(self, finger, bend_percent, tilt_degrees=0.0, speed=MAX_SPEED):
        """Bend 0 = fully open, 100 = fully closed. Tilt +/-30 deg moves the finger sideways."""
        bend = _clamp(float(bend_percent), 0.0, 100.0)
        tilt = _clamp(float(tilt_degrees), -TILT_LIMIT, TILT_LIMIT)
        flex = FLEX_OPEN + (FLEX_CLOSED - FLEX_OPEN) * bend / 100.0
        # The two servos turn opposite ways to bend, the same way to tilt.
        self.move_finger(finger, flex + tilt, -flex + tilt, speed)

    def open(self):
        gesture_open(self)

    def close_connection(self):
        try:
            self.open()
            time.sleep(0.5)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Named gestures - ported from PythonExample/AmazingHand_Demo.py (right hand)
# ---------------------------------------------------------------------------

def gesture_open(h):
    for f in FINGERS:
        h.move_finger(f, -35, 35, MAX_SPEED)


def gesture_close(h):
    h.move_finger("index", 90, -90, CLOSE_SPEED)
    h.move_finger("middle", 90, -90, CLOSE_SPEED)
    h.move_finger("ring", 90, -90, CLOSE_SPEED)
    h.move_finger("thumb", 90, -90, CLOSE_SPEED + 1)


def gesture_open_progressive(h):
    for i, f in enumerate(FINGERS):
        if i:
            time.sleep(0.2)
        h.move_finger(f, -35, 35, MAX_SPEED - 2)


def gesture_spread(h):
    h.move_finger("index", 4, 90, MAX_SPEED)
    h.move_finger("middle", -32, 32, MAX_SPEED)
    h.move_finger("ring", -90, -4, MAX_SPEED)
    h.move_finger("thumb", -90, -4, MAX_SPEED)


def gesture_clench(h):
    h.move_finger("index", -60, 0, MAX_SPEED)
    h.move_finger("middle", -35, 35, MAX_SPEED)
    h.move_finger("ring", 0, 70, MAX_SPEED)
    h.move_finger("thumb", -4, 90, MAX_SPEED)


def gesture_point(h):
    h.move_finger("index", -40, 40, MAX_SPEED)
    h.move_finger("middle", 90, -90, MAX_SPEED)
    h.move_finger("ring", 90, -90, MAX_SPEED)
    h.move_finger("thumb", 90, -90, MAX_SPEED)


def gesture_no_no(h):
    gesture_point(h)
    for _ in range(3):
        time.sleep(0.2)
        h.move_finger("index", -10, 80, MAX_SPEED)
        time.sleep(0.2)
        h.move_finger("index", -80, 10, MAX_SPEED)
    h.move_finger("index", -35, 35, MAX_SPEED)
    time.sleep(0.4)


def gesture_ok(h):
    h.move_finger("index", 50, -50, MAX_SPEED)
    h.move_finger("middle", 0, 0, MAX_SPEED)
    h.move_finger("ring", -20, 20, MAX_SPEED)
    h.move_finger("thumb", 65, 12, MAX_SPEED)


def gesture_victory(h):
    h.move_finger("index", -15, 65, MAX_SPEED)
    h.move_finger("middle", -65, 15, MAX_SPEED)
    h.move_finger("ring", 90, -90, MAX_SPEED)
    h.move_finger("thumb", 90, -90, MAX_SPEED)


def gesture_scissors(h):
    gesture_victory(h)
    for _ in range(3):
        time.sleep(0.2)
        h.move_finger("index", -50, 20, MAX_SPEED)
        h.move_finger("middle", -20, 50, MAX_SPEED)
        time.sleep(0.2)
        h.move_finger("index", -15, 65, MAX_SPEED)
        h.move_finger("middle", -65, 15, MAX_SPEED)


def gesture_pinch(h):
    h.move_finger("index", 90, -90, MAX_SPEED)
    h.move_finger("middle", 90, -90, MAX_SPEED)
    h.move_finger("ring", 90, -90, MAX_SPEED)
    h.move_finger("thumb", 0, -75, MAX_SPEED)


def gesture_middle_finger(h):
    h.move_finger("index", 90, -90, MAX_SPEED)
    h.move_finger("middle", -35, 35, MAX_SPEED)
    h.move_finger("ring", 90, -90, MAX_SPEED)
    h.move_finger("thumb", 0, -75, MAX_SPEED)


GESTURES = {
    "open": (gesture_open, "All fingers straight and open."),
    "close": (gesture_close, "Make a fist."),
    "open_progressive": (gesture_open_progressive, "Open the fingers one after another."),
    "spread": (gesture_spread, "Open hand with fingers spread apart."),
    "clench": (gesture_clench, "Open hand with fingers squeezed together."),
    "point": (gesture_point, "Point with the index finger, others closed."),
    "no_no": (gesture_no_no, "Point and wag the index finger side to side ('no no no')."),
    "ok": (gesture_ok, "OK / 'perfect' sign: thumb and index make a circle."),
    "victory": (gesture_victory, "Peace / victory sign: index and middle up in a V."),
    "scissors": (gesture_scissors, "Victory sign that snips index and middle like scissors."),
    "pinch": (gesture_pinch, "Fingers closed, thumb pinched against them."),
    "middle_finger": (gesture_middle_finger, "Rude gesture: only the middle finger up."),
}
