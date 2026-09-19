# Asteroids 2026

A classic, updated to meet the expectations of gamers in 2026 — **100% procedural**. Every sprite, glow, and sound is generated at runtime; there are no external assets.

## Files

| File | Description |
|------|-------------|
| `asteroids.py` | The entire game (single file, ~1370 lines) |
| `highscore.txt` | Persistent best score, auto-saved next to the script |
| `stats.txt` | Persistent stats (games played, best combo, saucers/bosses destroyed) |

## Requirements

- Python 3
- [pygame](https://www.pygame.org/)

```bash
pip install pygame
```

## Run

```bash
python asteroids.py
```

Headless self-test (runs 300 frames with dummy video/audio drivers, then prints `SELFTEST OK`):

```bash
python asteroids.py --selftest
```

## Controls

| Key | Action |
|-----|--------|
| Arrow keys / WASD | Steer & thrust |
| Space | Fire (also starts the game from the menu) |
| P | Pause / resume |
| M | Mute / unmute |
| F | Toggle fullscreen |
| - / + | Master volume down / up |
| ESC | Return to menu / quit |
| Enter | Start / restart |

## Gameplay

- **Waves:** each wave spawns `3 + level` large asteroids; clear them all to advance. Asteroids get faster as the level rises.
- **Scoring:** large = 20, medium = 50, small = 100. Chained kills within 2 seconds build a **combo multiplier up to x8** (shown in the HUD). **Near-misses** (flying close to an asteroid without hitting it) pay +5 each.
- **Lives:** 3 lives, capped at 5. **Bonus lives** come at escalating milestones — 10,000, then 30,000, then 60,000 (each step grows by 10,000). If you've lost a life and are below the cap, passing a milestone awards a life again. The HUD shows the next 1UP threshold (e.g. "1UP - next at 30000"), and each award is announced with a fanfare and floating text.
- **High score** is shown in the HUD and menu and saved to `highscore.txt` on quit / game over. Persistent **stats** (games, best combo, saucers, bosses) are saved to `stats.txt` and shown in the menu.
- **Flying saucer:** every ~10–22 s a UFO crosses the screen — it never stops, weaving in and out around asteroids (and swerving on its own even in open space) while a quiet warbling hum plays for the duration of its pass. It fires aimed magenta shots at your ship the whole way. Shoot it down for **500 points** (combo multiplier applies) and it **drops a power-up** (a guaranteed Nuke from wave 5 on). Colliding with the saucer damages you, and the shield power-up deflects it away.
- **Mothership boss:** every 5th wave a large mothership (HP bar above it) drifts across the top, firing three-way aimed spreads. It starts at **25 hits** to kill and gains **+25 HP for every previous mothership defeated** (25, 50, 75, …). It survives the Nuke. Destroy it for **2000 points** and up to two power-ups.
- **Power-up economy:** asteroids drop power-ups ~8% of the time, and at most **3 power-ups** are ever on screen at once (saucer/boss drops respect the cap too).

## Power-ups

Dropped by destroyed asteroids (~8% chance), by shot-down saucers, and by the mothership when destroyed (at most 3 on screen at once). Collected by flying over them; they blink before expiring.

| Letter | Name | Effect | Duration |
|--------|------|--------|----------|
| **R** | Rapid fire | Doubles fire rate | 8 s |
| **D** | Double shot | Two parallel shots | 10 s |
| **S** | Spread shot | Three-way fan | 10 s |
| **B** | Shield | Destroys asteroids on contact (score + splits) and gently pushes your ship away | 12 s |
| **T** | Time warp | Slows the world to 45% speed | 6 s |
| **N** | Nuke | Destroys every asteroid on screen (white flash) | instant |
| **W** | Weapon up | 3-shot laser tier (stacks, max x3; re-picking refreshes the timer) | 120 s |
| **M** | Magnet | Pulls nearby power-ups toward you | 10 s |

## Features

- **Procedural everything:** nebula background, parallax starfield, jagged asteroid sprites, ship, glow sprites, and all sound effects (lasers, explosions, thrust loop, UI chimes) are synthesized at runtime.
- **Sector shifts:** every 3 waves the background regenerates — a fresh nebula palette and starfield (announced with a "SECTOR SHIFT" banner and a warp-flash transition).
- **Kill-streak audio:** the laser pitch rises with your combo multiplier.
- **Ship death debris:** when you're hit, the ship breaks into spinning hull fragments that drift and fade.
- **Juice:** particle bursts, screen shake, floating score text, afterburner trail, blinking invulnerability, slow-motion tint, pulsing power-up indicators.
- **Shield physics:** a shielded asteroid contact counts as a hit on the asteroid — it explodes, splits, and scores — while the ship is only gently pushed away (low impulse).
- **Performance:** glow sprites are generated once and cached (quantized), so per-frame glow blits are cheap.
- **States:** menu (with drifting ambient asteroids, stats readout), play, pause, game over.
