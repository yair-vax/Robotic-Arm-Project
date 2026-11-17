"""Chat with the AmazingHand: type what you want, Gemini makes the hand do it.

    python llm_hand.py --dry-run      # no hand connected: print servo commands
    python llm_hand.py --port COM3    # drive the real hand
    python llm_hand.py --list-models  # show the Gemini models your key can use

Needs a free Gemini API key (https://aistudio.google.com/apikey) in the
GEMINI_API_KEY environment variable.
"""

import argparse
import time

from google import genai
from google.genai import errors, types

from hand import FINGERS, GESTURES, Hand, MAX_SPEED, SERIAL_PORT

# Flash-lite: works on the free tier, fast, and good enough for picking hand moves.
# Run with --list-models to see others, then pass --model <name>.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_TOOL_ROUNDS = 25      # safety cap on tool rounds per message
MAX_WAIT_SECONDS = 5.0

SYSTEM_PROMPT = f"""You control a physical robot hand (the AmazingHand, a right hand) through tools.
The person types what they want the hand to do; you make it happen with the tools.

The hand has exactly 4 fingers: {", ".join(FINGERS)}. There is no pinky. Each finger has two motions:
- bend_percent: 0 = straight/open, 100 = fully curled/closed.
- tilt_degrees: -30 to 30, moves the finger sideways (spread or squeeze together). Use 0 normally.
- speed: 1 (slow) to {MAX_SPEED} (fast).

Use do_gesture when one of the named gestures matches. Otherwise build the pose with set_fingers,
moving several fingers in one call. For sequences (counting, waving, dancing), alternate set_fingers
or do_gesture with wait. Request the whole sequence at once (several function calls in one reply)
when you can. Keep total motion for one request under about 20 seconds.

If a request is impossible for this hand (e.g. moving a pinky, wrist or arm, or picking things up
on its own), say so briefly and offer the closest thing it can do. After acting, reply with one
short sentence describing what the hand did."""

# Tool definitions (JSON Schema for each function's arguments)
TOOLS = [
    {
        "name": "do_gesture",
        "description": "Perform a named, pre-tuned hand gesture. Available: "
        + "; ".join(f"{name}: {desc}" for name, (_, desc) in GESTURES.items()),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": list(GESTURES)},
            },
            "required": ["name"],
        },
    },
    {
        "name": "set_fingers",
        "description": "Move one or more fingers to a custom pose at the same time. "
        "Fingers not listed keep their current position.",
        "parameters": {
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
                    },
                },
                "speed": {
                    "type": "integer",
                    "description": f"1 (slow) to {MAX_SPEED} (fast).",
                },
            },
            "required": ["moves", "speed"],
        },
    },
    {
        "name": "wait",
        "description": f"Pause between moves, up to {MAX_WAIT_SECONDS:g} seconds. "
        "Use it so a pose is visible before the next one.",
        "parameters": {
            "type": "object",
            "properties": {"seconds": {"type": "number"}},
            "required": ["seconds"],
        },
    },
    {
        "name": "relax",
        "description": "Return the hand to a relaxed open position.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def run_tool(hand, name, args):
    """Execute one tool call on the hand. Returns a short result string for the model."""
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


def make_config():
    declarations = [
        types.FunctionDeclaration(
            name=t["name"], description=t["description"], parameters_json_schema=t["parameters"]
        )
        for t in TOOLS
    ]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=declarations)],
        # We run the tools ourselves (they move real hardware), so turn off auto-calling.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )


def new_chat(client, model, history=None):
    return client.chats.create(model=model, config=make_config(), history=history or [])


def handle_message(client, model, chat, hand, user_text):
    """Send one user message and keep running tools until the model is done.

    Returns the chat to use next (a fresh copy if this turn failed part-way).
    """
    history_before = chat.get_history()
    try:
        response = chat.send_message(user_text)
        for _ in range(MAX_TOOL_ROUNDS):
            calls = response.function_calls
            if not calls:
                text = (response.text or "").strip()
                print(f"Gemini: {text or '(done)'}")
                return chat

            results = []
            for call in calls:
                try:
                    output = run_tool(hand, call.name, dict(call.args or {}))
                    payload = {"result": output}
                except Exception as exc:  # report hand/argument errors back to the model
                    payload = {"error": str(exc)}
                results.append(types.Part.from_function_response(name=call.name, response=payload))
            response = chat.send_message(results)

        print("Gemini: (stopped - too many steps for one request)")
        hand.open()
        return new_chat(client, model, history_before)

    except errors.ClientError as exc:
        if exc.code == 429:
            print("Error: free-tier limit reached (too many requests). Wait a minute, "
                  "or try again tomorrow if the daily quota is used up.")
        elif exc.code in (400, 401, 403) and "key" in str(exc.message).lower():
            print("Error: API key missing or invalid. Set GEMINI_API_KEY (see README).")
        elif exc.code == 404:
            print(f"Error: model '{model}' can't be used: {exc.message}\n"
                  "Run with --list-models to see other names, then use --model <name>.")
        else:
            print(f"API error {exc.code}: {exc.message}")
    except errors.APIError as exc:
        print(f"Gemini server error {exc.code}: {exc.message}\n"
              f"Try again in a moment, or start with a different --model (default {DEFAULT_MODEL}).")
    except OSError:
        print("Error: could not reach the Gemini API - check your internet connection.")

    # Roll back this turn so the conversation stays valid.
    return new_chat(client, model, history_before)


def list_models(client):
    print("Models your key can use for chat:")
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []):
            print("  ", m.name.removeprefix("models/"))


def main():
    parser = argparse.ArgumentParser(description="Control the AmazingHand by chatting with Gemini.")
    parser.add_argument("--port", default=SERIAL_PORT, help=f"serial port (default {SERIAL_PORT})")
    parser.add_argument("--dry-run", action="store_true", help="print servo commands, no hardware")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Gemini model (default {DEFAULT_MODEL})")
    parser.add_argument("--list-models", action="store_true", help="list available models and exit")
    args = parser.parse_args()

    try:
        client = genai.Client()  # reads GEMINI_API_KEY
    except ValueError:
        print("Error: no API key found. Set GEMINI_API_KEY (see LLMControl/README.md).")
        return

    if args.list_models:
        list_models(client)
        return

    hand = Hand(port=args.port, dry_run=args.dry_run)
    chat = new_chat(client, args.model)

    print(f"AmazingHand + Gemini ({args.model}). Tell the hand what to do (type 'quit' to exit).")
    if args.dry_run:
        print("(dry run: no hardware, servo commands are printed)")

    try:
        while True:
            user_text = input("\nYou: ").strip()
            if not user_text:
                continue
            if user_text.lower() in {"quit", "exit", "q"}:
                break
            chat = handle_message(client, args.model, chat, hand, user_text)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        print("Opening hand and exiting.")
        hand.close_connection()


if __name__ == "__main__":
    main()
