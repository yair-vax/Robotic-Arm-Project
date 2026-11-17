# LLM Control: talk to the AmazingHand

Type what you want the hand to do and Google Gemini makes it happen, using the free Gemini API tier:

```
You: make a peace sign
  [hand] gesture: victory
Gemini: The hand is showing a peace sign.

You: count to three slowly
  [hand] set: index 100% open, middle 0% open, ring 0% open, thumb 0% open (speed 4)
  [hand] wait 1.0s
  ...
```

Gemini reads your message and calls functions that move the hand: named gestures (fist, point, OK,
victory, ...) or custom finger poses (how open each finger is and how far it tilts). Every command
goes through `hand.py`, which clamps angles and speed, so the model can't push a servo past its limits.

**Finger opening, in percent:** 100% = fully open (straight), 0% = fully closed (curled into the
palm), 50% = half closed. 100% uses the same servo angles as `OpenHand()` in the demo, and 0% the
same as `CloseHand()`. Tilt (±30°) moves a finger sideways and is normally 0.

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

## Quick start: exactly what to type

Open a terminal in VS Code (**Terminal > New Terminal**). It opens in the `AmazingHand-main`
folder. If it doesn't, go there first:

```
cd C:\Users\yairv\Desktop\AmazingHand-main
```

### Dry run (no hand connected)

Nothing moves. Every servo command is printed on the screen instead.

1. Start the program:
   ```
   python LLMControl/llm_hand.py --dry-run
   ```
2. Wait for `You:`, then type a request and press **Enter**:
   ```
   You: make a peace sign
   ```
3. Type more requests the same way. When you're done, type:
   ```
   You: quit
   ```

### Real hand (connected on COM3)

1. Plug the hand's USB serial adapter into the PC and turn on the servos' power supply.
2. Start the program:
   ```
   python LLMControl/llm_hand.py --port COM3
   ```
   If your hand is on a different port, use that instead (e.g. `--port COM5`). The port is
   listed in **Device Manager > Ports (COM & LPT)**.
3. Wait for `You:`, then type a request and press **Enter**:
   ```
   You: make a fist
   ```
4. When you're done, type `quit`. The hand opens before the program closes. Ctrl+C does the same.

### Requests go at the `You:` prompt, not on the command line

```
python LLMControl/llm_hand.py --dry-run make a peace sign   <- wrong: the program rejects it
python LLMControl/llm_hand.py --dry-run                     <- right: start it, then type at You:
```

### If something goes wrong

| You see | What to do |
|---|---|
| `Python was not found` | Close VS Code completely and reopen it (Python was added to PATH after VS Code started). |
| `no API key found` | Run `setx GEMINI_API_KEY "your-key-here"` once, then close and reopen VS Code. Use `setx`; PowerShell's `Set` doesn't work. |
| `free-tier limit reached` | Wait a minute, or until tomorrow if the daily quota is used up. |
| `server error 503 ... high demand` | Try again in a moment, or start with another model: `--model gemini-3.1-flash-lite` |
| `model ... can't be used` | Run `python LLMControl/llm_hand.py --list-models` and pick a name with `--model <name>`. |

## Things to try

- `make a fist`, `open`, `point`, `ok sign`, `peace`
- `bend only your index halfway`
- `count to 3 slowly`
- `wave no with your finger, then relax`
- `do that again but slower` (it remembers the conversation)

## Free tier notes

- The default model is `gemini-3.5-flash-lite`: it works on the free tier and handles hand
  commands well. To see what your key can use, run `python LLMControl/llm_hand.py --list-models`,
  then pick one with `--model <name>`, e.g. `--model gemini-3.8-flash` (smarter, but often
  busy with "high demand" errors on the free tier).
- The free tier has per-minute and per-day request limits, and Google changes them often. One
  command uses about 2-3 requests. If you hit the limit you'll see a "free-tier limit reached"
  message: wait a minute, or until the next day.
- On the free tier, Google may use your prompts to improve its models. Don't type anything private.

## Notes

- Settings for one right hand on servo IDs 1-8. For a left hand, the side-tilt gestures
  (`spread`, `clench`, `ok`, `victory`, `scissors`, `pinch`) would need the left-hand values from
  `AmazingHand_Demo.py`.
