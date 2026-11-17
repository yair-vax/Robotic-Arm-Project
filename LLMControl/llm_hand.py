"""Chat with the AmazingHand: type what you want, Claude makes the hand do it.

    python llm_hand.py --dry-run      # no hand connected: print servo commands
    python llm_hand.py --port COM3    # drive the real hand

Needs an Anthropic API key in the ANTHROPIC_API_KEY environment variable
(or a profile from `ant auth login`).
"""

import argparse
import json
import time

import anthropic

from hand import FINGERS, GESTURES, Hand, MAX_SPEED, SERIAL_PORT

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOOL_ROUNDS = 25      # safety cap on tool calls per message
MAX_WAIT_SECONDS = 5.0

SYSTEM_PROMPT = f"""You control a physical robot hand (the AmazingHand, a right hand) through tools.
The person types what they want the hand to do; you make it happen with the tools.

The hand has exactly 4 fingers: {", ".join(FINGERS)}. There is no pinky. Each finger has two motions:
- bend_percent: 0 = straight/open, 100 = fully curled/closed.
- tilt_degrees: -30 to 30, moves the finger sideways (spread or squeeze together). Use 0 normally.
- speed: 1 (slow) to {MAX_SPEED} (fast).

Use do_gesture when one of the named gestures matches. Otherwise build the pose with set_fingers,
moving several fingers in one call. For sequences (counting, waving, dancing), alternate set_fingers
or do_gesture with wait. Keep total motion for one request under about 20 seconds.

If a request is impossible for this hand (e.g. moving a pinky, wrist or arm, or picking things up
on its own), say so briefly and offer the closest thing it can do. After acting, reply with one
short sentence describing what the hand did."""

TOOLS = [
    {
        "name": "do_gesture",
        "description": "Perform a named, pre-tuned hand gesture. Available: "
        + "; ".join(f"{name}: {desc}" for name, (_, desc) in GESTURES.items()),
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": list(GESTURES)},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_fingers",
        "description": "Move one or more fingers to a custom pose at the same time. "
        "Fingers not listed keep their current position.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "moves": {
                    "type": "array",
                    "description": "One entry per finger to move.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "finger": {"type": "string", "enum": FINGERS},
                            "bend_percent": {
                                "type": "number",
                                "description": "0 = open/straight, 100 = fully closed.",
                            },
                            "tilt_degrees": {
                                "type": "number",
                                "description": "Sideways tilt, -30 to 30. Usually 0.",
                            },
                        },
                        "required": ["finger", "bend_percent", "tilt_degrees"],
                        "additionalProperties": False,
                    },
                },
                "speed": {
                    "type": "integer",
                    "description": f"1 (slow) to {MAX_SPEED} (fast).",
                },
            },
            "required": ["moves", "speed"],
            "additionalProperties": False,
        },
    },
    {
        "name": "wait",
        "description": f"Pause between moves, up to {MAX_WAIT_SECONDS:g} seconds. "
        "Use it so a pose is visible before the next one.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
            "required": ["seconds"],
            "additionalProperties": False,
        },
    },
    {
        "name": "relax",
        "description": "Return the hand to a relaxed open position.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
]


def run_tool(hand, name, args):
    """Execute one tool call on the hand. Returns a short result string for Claude."""
    if name == "do_gesture":
        gesture = args["name"]
        if gesture not in GESTURES:
            raise ValueError(f"Unknown gesture '{gesture}'.")
        print(f"  [hand] gesture: {gesture}")
        GESTURES[gesture][0](hand)
        return f"Did gesture '{gesture}'."

    if name == "set_fingers":
        speed = max(1, min(int(args.get("speed", MAX_SPEED)), MAX_SPEED))
        parts = []
        for move in args["moves"]:
            bend = max(0.0, min(float(move["bend_percent"]), 100.0))
            hand.set_finger(move["finger"], bend, move.get("tilt_degrees", 0), speed)
            parts.append(f"{move['finger']} {bend:.0f}%")
        print(f"  [hand] set: {', '.join(parts)} (speed {speed})")
        return "Moved: " + ", ".join(parts) + "."

    if name == "wait":
        seconds = max(0.0, min(float(args["seconds"]), MAX_WAIT_SECONDS))
        print(f"  [hand] wait {seconds:.1f}s")
        time.sleep(seconds)
        return f"Waited {seconds:.1f}s."

    if name == "relax":
        print("  [hand] relax")
        hand.open()
        return "Hand relaxed (open)."

    raise ValueError(f"Unknown tool '{name}'.")


def handle_message(client, hand, messages, user_text):
    """Send one user message and keep calling tools until Claude is done."""
    turn_start = len(messages)
    messages.append({"role": "user", "content": user_text})

    try:
        for _ in range(MAX_TOOL_ROUNDS):
            response = client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
                output_config={"effort": "low"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )

            if response.stop_reason == "refusal":
                del messages[turn_start:]
                print("Claude: Sorry, I can't help with that one.")
                return

            messages.append({"role": "assistant", "content": response.content})

            tool_calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not tool_calls:
                text = " ".join(b.text for b in response.content if b.type == "text").strip()
                if response.stop_reason == "max_tokens":
                    text += " (reply was cut off)"
                print(f"Claude: {text or '(done)'}")
                return

            results = []
            for call in tool_calls:
                try:
                    args = call.input if isinstance(call.input, dict) else json.loads(call.input)
                    output, is_error = run_tool(hand, call.name, args), False
                except Exception as exc:  # report hand/argument errors back to Claude
                    output, is_error = f"Error: {exc}", True
                results.append({
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": output,
                    "is_error": is_error,
                })
            messages.append({"role": "user", "content": results})

        print("Claude: (stopped - too many steps for one request)")
        hand.open()
        messages.append({"role": "assistant", "content": "I stopped because the sequence was too long."})

    except anthropic.AuthenticationError:
        del messages[turn_start:]
        print("Error: API key missing or invalid. Set ANTHROPIC_API_KEY (see README).")
    except anthropic.RateLimitError:
        del messages[turn_start:]
        print("Error: rate limited by the API - wait a moment and try again.")
    except anthropic.APIStatusError as exc:
        del messages[turn_start:]
        print(f"API error {exc.status_code}: {exc.message}")
    except anthropic.APIConnectionError:
        del messages[turn_start:]
        print("Error: could not reach the Claude API - check your internet connection.")


def main():
    parser = argparse.ArgumentParser(description="Control the AmazingHand by chatting with Claude.")
    parser.add_argument("--port", default=SERIAL_PORT, help=f"serial port (default {SERIAL_PORT})")
    parser.add_argument("--dry-run", action="store_true", help="print servo commands, no hardware")
    args = parser.parse_args()

    hand = Hand(port=args.port, dry_run=args.dry_run)
    client = anthropic.Anthropic()
    messages = []

    print("AmazingHand + Claude. Tell the hand what to do (type 'quit' to exit).")
    if args.dry_run:
        print("(dry run: no hardware, servo commands are printed)")

    try:
        while True:
            user_text = input("\nYou: ").strip()
            if not user_text:
                continue
            if user_text.lower() in {"quit", "exit", "q"}:
                break
            handle_message(client, hand, messages, user_text)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        print("Opening hand and exiting.")
        hand.close_connection()


if __name__ == "__main__":
    main()
