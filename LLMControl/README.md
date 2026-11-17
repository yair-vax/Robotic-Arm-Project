# LLM Control: talk to the AmazingHand

Type what you want the hand to do and Claude makes it happen:

```
You: make a peace sign
  [hand] gesture: victory
Claude: The hand is showing a peace sign.

You: count to three slowly
  [hand] set: index 0%, middle 100%, ring 100%, thumb 100% (speed 4)
  [hand] wait 1.0s
  ...
```

Claude reads your message and calls tools that move the hand: named gestures (fist, point, OK,
victory, ...) or custom finger poses (how much each finger bends and tilts). Every command goes
through `hand.py`, which clamps angles and speed, so Claude can't push a servo past its limits.

## Setup

1. **Python 3.10+** and the packages:
   ```
   pip install -r LLMControl/requirements.txt
   ```
2. **API key.** Create one at https://console.anthropic.com, then set it once (open a new terminal afterwards):
   ```
   setx ANTHROPIC_API_KEY "sk-ant-..."
   ```
3. **Calibration.** Put your servo middle positions in `MIDDLE_POS` at the top of `hand.py`
   (same values as `MiddlePos` in `PythonExample/AmazingHand_Demo.py`). Change `SERIAL_PORT` if
   your hand isn't on `COM3`.

## Run

Try it without the hand first. Servo commands are printed instead of sent:

```
python LLMControl/llm_hand.py --dry-run
```

With the hand connected:

```
python LLMControl/llm_hand.py --port COM3
```

Type `quit` (or press Ctrl+C) to exit. The hand opens before the program closes.

## Things to try

- `make a fist`, `open`, `point`, `ok sign`, `peace`
- `bend only your index halfway`
- `count to 3 slowly`
- `wave no with your finger, then relax`
- `do that again but slower` (it remembers the conversation)

## Notes

- Model: `claude-opus-5-5` at low effort, for quick replies. Each message costs a fraction of a
  cent. Change `MODEL` at the top of `llm_hand.py` to try another model.
- If Claude declines a request, a server-side fallback retries it on another model automatically.
- Settings for one right hand on servo IDs 1-8. For a left hand, the side-tilt gestures
  (`spread`, `clench`, `ok`, `victory`, `scissors`, `pinch`) would need the left-hand values from
  `AmazingHand_Demo.py`.
