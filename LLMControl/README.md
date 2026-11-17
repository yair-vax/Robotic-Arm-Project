# LLM Control: talk to the AmazingHand

Type what you want the hand to do and Google Gemini makes it happen, using the free Gemini API tier:

```
You: make a peace sign
  [hand] gesture: victory
Gemini: The hand is showing a peace sign.

You: count to three slowly
  [hand] set: index 0%, middle 100%, ring 100%, thumb 100% (speed 4)
  [hand] wait 1.0s
  ...
```

Gemini reads your message and calls functions that move the hand: named gestures (fist, point, OK,
victory, ...) or custom finger poses (how much each finger bends and tilts). Every command goes
through `hand.py`, which clamps angles and speed, so the model can't push a servo past its limits.

## Setup

1. **Python 3.10+** and the packages:
   ```
   pip install -r LLMControl/requirements.txt
   ```
2. **Free API key.** Sign in at https://aistudio.google.com/apikey with a Google account and click
   *Create API key*. No credit card is needed. Then set it once and open a new terminal afterwards:
   ```
   setx GEMINI_API_KEY "your-key-here"
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

## Free tier notes

- The default model is `gemini-flash-latest`, which always points at Google's current Flash model.
  To see what your key can use, run `python LLMControl/llm_hand.py --list-models`, then pick one
  with `--model <name>` (a "flash-lite" model usually has the highest free limits).
- The free tier has per-minute and per-day request limits, and Google changes them often. One
  command uses about 2-3 requests. If you hit the limit you'll see a "free-tier limit reached"
  message: wait a minute, or until the next day.
- On the free tier, Google may use your prompts to improve its models. Don't type anything private.

## Notes

- Settings for one right hand on servo IDs 1-8. For a left hand, the side-tilt gestures
  (`spread`, `clench`, `ok`, `victory`, `scissors`, `pinch`) would need the left-hand values from
  `AmazingHand_Demo.py`.
