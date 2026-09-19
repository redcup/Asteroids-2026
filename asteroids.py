#!/usr/bin/env python3
"""
ASTEROIDS 2026 — a classic, updated to meet the expectations of gamers in 2026.
100% procedural: every sprite, glow, and sound is generated at runtime.
No external assets.

Controls:
  Arrow keys / WASD ... steer & thrust
  Space ............... fire
  P ................. pause
  M ................. mute
  ESC ............... menu / quit
"""

from array import array
import math
import os
import random
import sys

import pygame

# ---------------------------------------------------------------- constants
W, H = 1280, 720
FPS = 60
SR = 44100  # sample rate

WHITE = (255, 255, 255)
YELLOW = (255, 220, 120)
ORANGE = (255, 140, 50)
GREEN = (80, 255, 140)
CYAN = (80, 220, 255)
BLUE = (90, 140, 255)
PURPLE = (200, 110, 255)
RED = (255, 80, 80)

HS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscore.txt")
STATS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.txt")

# ---------------------------------------------------------------- tiny helpers

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def wrap(x, y):
    if x < -40: x += W + 80
    if x > W + 40: x -= W + 80
    if y < -40: y += H + 80
    if y > H + 40: y -= H + 80
    return x, y

def lerp_color(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

_GLOW_CACHE = {}
def make_glow(radius, color, peak_alpha=160):
    """Radial additive glow sprite (cached; peak_alpha quantized)."""
    key = (int(radius), tuple(color), (int(peak_alpha) // 8) * 8)
    s = _GLOW_CACHE.get(key)
    if s is None:
        s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for i in range(radius, 0, -1):
            a = int(peak_alpha * (1 - i / radius) ** 2.2)
            pygame.draw.circle(s, (*color, a), (radius, radius), i)
        _GLOW_CACHE[key] = s
    return s

# ---------------------------------------------------------------- procedural sound
class Sfx:
    def __init__(self):
        self.ok = False
        self.sounds = {}
        self.master = 0.8
        self.muted = False
        self.thrust = None
        self.thrust_playing = False
        self.saucer = None
        self.saucer_playing = False
        try:
            pygame.mixer.pre_init(SR, -16, 1, 512)
            pygame.mixer.init()
            self.ok = True
            self.build()
        except Exception as e:
            print("audio unavailable:", e)

    def _snd(self, samples):
        arr = array("h", [clamp(int(s * 32767), -32768, 32767) for s in samples])
        return pygame.mixer.Sound(buffer=arr.tobytes())

    def _tone(self, dur, f0, f1=None, vol=0.5, shape="sine"):
        n = int(SR * dur)
        f1 = f1 or f0
        out = []
        phase = 0.0
        for i in range(n):
            t = i / n
            f = f0 + (f1 - f0) * t
            phase += 2 * math.pi * f / SR
            if shape == "sine":
                v = math.sin(phase)
            elif shape == "saw":
                v = 2 * ((phase / (2 * math.pi)) % 1) - 1
            else:
                v = math.copysign(1, math.sin(phase))
            out.append(v * vol * (1 - t) ** 1.5)
        return out

    def _noise(self, dur, vol=0.5, lp=0.1, decay=2.0):
        n = int(SR * dur)
        out, y = [], 0.0
        for i in range(n):
            x = random.uniform(-1, 1)
            y += lp * (x - y)
            t = i / n
            out.append(y * vol * (1 - t) ** decay)
        return out

    def _warble(self, dur, f0, fdev, wfreq, vol=0.5):
        """Vibrato tone: frequency wobbles, edge-faded so the loop is seamless."""
        n = int(SR * dur)
        out = []
        phase = 0.0
        for i in range(n):
            t = i / SR
            f = f0 + fdev * math.sin(2 * math.pi * wfreq * t)
            phase += 2 * math.pi * f / SR
            fade = min(1.0, i / (SR * 0.012), (n - i) / (SR * 0.012))
            out.append(math.sin(phase) * vol * fade)
        return out

    def _mix(self, *parts):
        n = max(len(p) for p in parts)
        out = [0.0] * n
        for p in parts:
            for i, v in enumerate(p):
                out[i] += v
        peak = max((abs(v) for v in out), default=1.0) or 1.0
        return [v / peak * 0.9 for v in out]

    def build(self):
        # laser bank: pitch rises with the kill-streak combo
        for i in range(5):
            self.sounds[f"laser{i}"] = self._snd(self._tone(0.13, 950 * (1 + 0.12 * i), 220 * (1 + 0.12 * i), 0.35, "saw"))
            self.sounds[f"laser{i}"].set_volume(0.55)
        self.sounds["explosion_s"] = self._snd(self._mix(self._noise(0.35, 0.6, 0.12), self._tone(0.3, 120, 40, 0.5)))
        self.sounds["explosion_s"].set_volume(0.7)
        self.sounds["explosion_m"] = self._snd(self._mix(self._noise(0.5, 0.7, 0.08), self._tone(0.45, 90, 30, 0.6)))
        self.sounds["explosion_m"].set_volume(0.8)
        self.sounds["explosion_l"] = self._snd(self._mix(self._noise(0.8, 0.8, 0.06), self._tone(0.7, 60, 25, 0.7)))
        self.sounds["explosion_l"].set_volume(0.9)
        self.sounds["ship"] = self._snd(self._mix(self._noise(1.0, 0.8, 0.05), self._tone(0.9, 200, 30, 0.6, "saw")))
        self.sounds["ship"].set_volume(1.0)
        self.sounds["power"] = self._snd(self._mix(
            self._tone(0.09, 523, 523, 0.5),
            self._tone(0.09, 659, 659, 0.5),
            self._tone(0.16, 784, 1046, 0.5)))
        self.sounds["power"].set_volume(0.6)
        self.sounds["shield"] = self._snd(self._tone(0.35, 300, 900, 0.4, "sine"))
        self.sounds["shield"].set_volume(0.6)
        self.sounds["nuke"] = self._snd(self._mix(
            self._noise(0.9, 0.9, 0.05), self._tone(0.8, 80, 300, 0.5, "saw")))
        self.sounds["nuke"].set_volume(0.9)
        self.sounds["ui"] = self._snd(self._tone(0.07, 880, 880, 0.3))
        self.sounds["ui"].set_volume(0.4)
        self.sounds["levelup"] = self._snd(self._mix(
            self._tone(0.1, 440, 440, 0.4), self._tone(0.1, 554, 554, 0.4),
            self._tone(0.22, 659, 880, 0.4)))
        self.sounds["levelup"].set_volume(0.5)
        # thrust loop (lowpass noise)
        self.thrust = self._snd(self._noise(0.5, 0.25, 0.04, 0.0))
        self.thrust.set_volume(0.35)
        # saucer warble loop (vibrato tone, deliberately quieter than other SFX)
        self.saucer = self._snd(self._warble(0.6, 200, 110, 4.0, 0.4))
        self.saucer.set_volume(0.25)

    def play(self, name, vol=None):
        if not self.ok or self.muted:
            return
        s = self.sounds.get(name)
        if s:
            if vol is not None:
                s.set_volume(clamp(vol * self.master, 0, 1))
            s.play()

    def thrust_on(self):
        if self.ok and not self.muted and not self.thrust_playing:
            self.thrust.play(loops=-1)
            self.thrust_playing = True

    def thrust_off(self):
        if self.thrust_playing:
            self.thrust.stop()
            self.thrust_playing = False

    def saucer_on(self):
        if self.ok and not self.muted and not self.saucer_playing:
            self.saucer.play(loops=-1)
            self.saucer_playing = True

    def saucer_off(self):
        if self.saucer_playing:
            self.saucer.stop()
            self.saucer_playing = False

    def toggle_mute(self):
        self.muted = not self.muted
        if self.muted:
            self.thrust_off()
            self.saucer_off()
        return self.muted

# ---------------------------------------------------------------- background
class Background:
    def __init__(self):
        self.stars = [[[] for _ in range(3)] for _ in range(1)]
        self.stars = [
            [pygame.math.Vector2(random.uniform(0, W), random.uniform(0, H)) for _ in range(90)],
            [pygame.math.Vector2(random.uniform(0, W), random.uniform(0, H)) for _ in range(50)],
            [pygame.math.Vector2(random.uniform(0, W), random.uniform(0, H)) for _ in range(22)],
        ]
        self.speeds = [0.15, 0.4, 0.9]
        self.nebula = self._make_nebula()
        self.vignette = pygame.Surface((W, H), pygame.SRCALPHA)
        for i in range(60):
            a = int(90 * (i / 60) ** 2)
            pygame.draw.rect(self.vignette, (0, 0, 10, a),
                             (0, 0, W, H), 0)
        # proper vignette: dark edges
        self.vignette = pygame.Surface((W, H), pygame.SRCALPHA)
        cx, cy = W / 2, H / 2
        maxd = math.hypot(cx, cy)
        for i in range(40):
            a = int(110 * (i / 40) ** 2.5)
            r = 6 + i * 4
            pygame.draw.ellipse(self.vignette, (0, 0, 12, a),
                               (cx - r * 1.35, cy - r * 0.95, r * 2.7, r * 1.9), 3)

    def _make_nebula(self):
        s = pygame.Surface((W, H))
        base = (6, 6, 18)
        s.fill(base)
        palette = [
            (40, 20, 90), (15, 40, 80), (70, 20, 60), (20, 50, 70), (50, 25, 90),
            (90, 30, 40), (30, 90, 60), (20, 60, 100), (100, 60, 30), (60, 20, 40),
        ]
        for _ in range(random.randint(4, 6)):
            bx, by = random.uniform(0, W), random.uniform(0, H)
            br = random.uniform(280, 500)
            col = random.choice(palette)
            for i in range(int(br), 0, -2):
                t = i / br
                a = int(46 * (1 - t) ** 2)
                c = lerp_color(base, col, (1 - t))
                pygame.draw.circle(s, c, (int(bx), int(by)), i)
        # sprinkle faint dust
        for _ in range(300):
            x, y = random.randint(0, W - 1), random.randint(0, H - 1)
            s.set_at((x, y), (random.randint(20, 55), random.randint(20, 50), random.randint(40, 80)))
        return s

    def regen(self):
        """New sector: fresh nebula and starfield (every 3 waves)."""
        self.nebula = self._make_nebula()
        self.stars = [
            [pygame.math.Vector2(random.uniform(0, W), random.uniform(0, H)) for _ in range(90)],
            [pygame.math.Vector2(random.uniform(0, W), random.uniform(0, H)) for _ in range(50)],
            [pygame.math.Vector2(random.uniform(0, W), random.uniform(0, H)) for _ in range(22)],
        ]

    def update(self, dt, drift=0.0):
        for i, layer in enumerate(self.stars):
            sp = self.speeds[i]
            for st in layer:
                st.y += sp * dt * 60 + drift * sp * dt * 60
                st.x -= drift * sp * dt * 60 * 0.5
                if st.y > H + 4: st.y = -4; st.x = random.uniform(0, W)
                if st.x < -4: st.x = W + 4
                if st.x > W + 4: st.x = -4

    def draw(self, s, t):
        s.blit(self.nebula, (0, 0))
        for i, layer in enumerate(self.stars):
            base = [40, 90, 160][i]
            tw = 0.7 + 0.3 * math.sin(t * (2 + i) + i)
            for j, st in enumerate(layer):
                a = int(base * tw * (0.7 + 0.3 * math.sin(t * 3 + j * 1.7)))
                sz = [1, 1, 2][i]
                c = (a, a, min(255, int(a * 1.1)))
                pygame.draw.rect(s, c, (st.x, st.y, sz, sz))
        s.blit(self.vignette, (0, 0))

# ---------------------------------------------------------------- particles
class Particles:
    def __init__(self):
        self.list = []
        self.buf = pygame.Surface((W, H), pygame.SRCALPHA)

    def burst(self, x, y, n, color, speed=180, life=0.8, size=3):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(speed * 0.2, speed)
            self.list.append({
                "p": pygame.math.Vector2(x, y),
                "v": pygame.math.Vector2(math.cos(a), math.sin(a)) * sp,
                "l": random.uniform(life * 0.5, life),
                "L": life, "c": color, "s": random.uniform(size * 0.5, size * 1.4),
            })

    def debris(self, x, y, n, color, life=1.6):
        """Spinning hull fragments."""
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            sp = random.uniform(60, 260)
            self.list.append({
                "p": pygame.math.Vector2(x, y),
                "v": pygame.math.Vector2(math.cos(a), math.sin(a)) * sp,
                "l": random.uniform(life * 0.6, life),
                "L": life, "c": color, "s": random.uniform(3, 7),
                "spin": True, "ang": random.uniform(0, 360),
                "rv": random.uniform(-360, 360),
            })

    def update(self, dt):
        for p in self.list:
            p["p"] += p["v"] * dt
            p["v"] *= (1 - 1.8 * dt)
            p["l"] -= dt
            if p.get("spin"):
                p["ang"] = (p["ang"] + p["rv"] * dt) % 360
        self.list = [p for p in self.list if p["l"] > 0]

    def draw(self, s):
        self.buf.fill((0, 0, 0, 0))
        for p in self.list:
            t = p["l"] / p["L"]
            c = lerp_color((255, 255, 255), p["c"], 1 - t)
            a = int(230 * t)
            if p.get("spin"):
                v = pygame.math.Vector2(1, 0).rotate(p["ang"]) * p["s"]
                pygame.draw.line(self.buf, (*c, a), p["p"] - v, p["p"] + v, 2)
            else:
                r = max(1, int(p["s"] * t))
                pygame.draw.circle(self.buf, (*c, a), (int(p["p"].x), int(p["p"].y)), r)
        s.blit(self.buf, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

# ---------------------------------------------------------------- sprites
def make_ship_sprite():
    s = pygame.Surface((64, 64), pygame.SRCALPHA)
    # glow
    g = make_glow(30, (120, 180, 255), 90)
    s.blit(g, (32 - 30, 32 - 30), special_flags=pygame.BLEND_RGBA_ADD)
    # hull
    pts = [(32, 10), (48, 52), (38, 46), (26, 46), (16, 52)]
    pygame.draw.polygon(s, (200, 220, 255), pts)
    pygame.draw.polygon(s, (90, 120, 200), pts, 2)
    # cockpit
    pygame.draw.circle(s, (140, 230, 255), (32, 28), 5)
    pygame.draw.circle(s, (60, 90, 160), (32, 28), 5, 2)
    # nose highlight
    pygame.draw.line(s, (255, 255, 255), (32, 10), (32, 22), 2)
    return s

def make_asteroid_sprite(radius, seed):
    rng = random.Random(seed)
    size = int(radius * 2 + 40)
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    g = make_glow(radius + 12, (255, 160, 100), 40)
    s.blit(g, (size // 2 - (radius + 12), size // 2 - (radius + 12)), special_flags=pygame.BLEND_RGBA_ADD)
    cx = cy = size // 2
    n = rng.randint(9, 13)
    pts = []
    for i in range(n):
        a = i / n * 2 * math.pi
        r = radius * rng.uniform(0.72, 1.05)
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    base = (95, 85, 80)
    pygame.draw.polygon(s, base, pts)
    # shading: darker half
    pygame.draw.polygon(s, (60, 55, 55), pts, 0)
    pygame.draw.polygon(s, (130, 118, 108), pts)
    pygame.draw.polygon(s, (210, 190, 170), pts, 2)
    # craters
    for _ in range(rng.randint(2, 4)):
        a = rng.uniform(0, 2 * math.pi)
        d = rng.uniform(0, radius * 0.5)
        pygame.draw.circle(s, (70, 62, 60), (int(cx + math.cos(a) * d), int(cy + math.sin(a) * d)), rng.randint(2, max(3, radius // 4)))
    return s

def make_saucer_sprite():
    s = pygame.Surface((96, 64), pygame.SRCALPHA)
    g = make_glow(42, (255, 90, 190), 70)
    s.blit(g, (48 - 42, 32 - 42), special_flags=pygame.BLEND_RGBA_ADD)
    # dome
    pygame.draw.ellipse(s, (220, 170, 255), (32, 12, 32, 28))
    pygame.draw.ellipse(s, (255, 210, 255), (32, 12, 32, 28), 2)
    # disc
    pygame.draw.ellipse(s, (170, 100, 210), (12, 30, 72, 22))
    pygame.draw.ellipse(s, (255, 140, 220), (12, 30, 72, 22), 2)
    # running lights
    for x in (22, 38, 58, 74):
        pygame.draw.circle(s, (255, 220, 120), (x, 41), 3)
    return s

def make_mothership_sprite():
    s = pygame.Surface((160, 120), pygame.SRCALPHA)
    g = make_glow(70, (255, 100, 80), 80)
    s.blit(g, (80 - 70, 60 - 70), special_flags=pygame.BLEND_RGBA_ADD)
    # domes
    pygame.draw.ellipse(s, (200, 120, 100), (35, 25, 40, 40))
    pygame.draw.ellipse(s, (255, 180, 140), (35, 25, 40, 40), 2)
    pygame.draw.ellipse(s, (200, 120, 100), (85, 25, 40, 40))
    pygame.draw.ellipse(s, (255, 180, 140), (85, 25, 40, 40), 2)
    # hull
    pygame.draw.ellipse(s, (150, 80, 70), (15, 45, 130, 50))
    pygame.draw.ellipse(s, (255, 150, 110), (15, 45, 130, 50), 2)
    # running lights
    for x in (30, 55, 80, 105, 130):
        pygame.draw.circle(s, (255, 220, 120), (x, 70), 4)
    return s

def make_powerup_sprite(letter, color):
    s = pygame.Surface((56, 56), pygame.SRCALPHA)
    g = make_glow(28, color, 110)
    s.blit(g, (28 - 28, 28 - 28), special_flags=pygame.BLEND_RGBA_ADD)
    pygame.draw.circle(s, (*color, 255), (28, 28), 16)
    pygame.draw.circle(s, (255, 255, 255), (28, 28), 16, 3)
    f = pygame.font.Font(None, 26)
    lc = (40, 40, 40) if min(color) > 200 else (255, 255, 255)
    t = f.render(letter, True, lc)
    s.blit(t, t.get_rect(center=(28, 28)))
    return s

# ---------------------------------------------------------------- entities
class Bullet:
    def __init__(self, x, y, ang, speed=620):
        self.p = pygame.math.Vector2(x, y)
        self.v = pygame.math.Vector2(math.cos(ang), math.sin(ang)) * speed
        self.life = 1.1
        self.trail = []

    def update(self, dt):
        self.trail.append(pygame.math.Vector2(self.p))
        if len(self.trail) > 6: self.trail.pop(0)
        self.p += self.v * dt
        self.p = pygame.math.Vector2(*wrap(self.p.x, self.p.y))
        self.life -= dt

    def draw(self, s):
        for i, tp in enumerate(self.trail):
            a = int(140 * i / len(self.trail))
            pygame.draw.circle(s, (255, 220, 120, a), (int(tp.x), int(tp.y)), 2)
        g = make_glow(8, YELLOW, 120)
        s.blit(g, (self.p.x - 8, self.p.y - 8), special_flags=pygame.BLEND_RGBA_ADD)
        pygame.draw.circle(s, (255, 255, 220), (int(self.p.x), int(self.p.y)), 3)

class Asteroid:
    RADIUS = {3: 52, 2: 30, 1: 16}
    SCORE = {3: 20, 2: 50, 1: 100}

    def __init__(self, x, y, size, speed=110):
        self.size = size
        self.r = self.RADIUS[size]
        self.p = pygame.math.Vector2(x, y)
        a = random.uniform(0, 2 * math.pi)
        self.v = pygame.math.Vector2(math.cos(a), math.sin(a)) * random.uniform(speed * 0.6, speed * 1.3)
        self.rot = random.uniform(0, 360)
        self.rv = random.uniform(-60, 60)
        self.nm_cd = 0
        self.sprite = make_asteroid_sprite(self.r, random.randint(0, 10**9))

    def update(self, dt):
        self.p += self.v * dt
        self.p = pygame.math.Vector2(*wrap(self.p.x, self.p.y))
        self.rot = (self.rot + self.rv * dt) % 360
        self.nm_cd = max(0, self.nm_cd - dt)

    def draw(self, s):
        rot = pygame.transform.rotate(self.sprite, -self.rot)
        s.blit(rot, (self.p.x - rot.get_width() / 2, self.p.y - rot.get_height() / 2))

    def split(self, rng):
        out = []
        if self.size > 1:
            for _ in range(2):
                a = rng.uniform(0, 2 * math.pi)
                sp = 110 + (4 - self.size) * 40
                out.append(Asteroid(self.p.x, self.p.y, self.size - 1, sp))
                out[-1].v = pygame.math.Vector2(math.cos(a), math.sin(a)) * sp * rng.uniform(0.8, 1.4)
        return out

class PowerUp:
    KINDS = [
        ("R", "rapid", ORANGE, 3),
        ("D", "double", GREEN, 3),
        ("S", "spread", CYAN, 3),
        ("B", "shield", BLUE, 2),
        ("T", "slow", PURPLE, 2),
        ("N", "nuke", RED, 1),
        ("W", "weapon", (255, 255, 255), 2),
        ("M", "magnet", (255, 120, 240), 1),
    ]

    def __init__(self, x, y, kind=None):
        if kind is not None:
            for letter, k, color, w in self.KINDS:
                if k == kind:
                    self.letter, self.kind, self.color = letter, k, color
                    break
        else:
            total = sum(k[3] for k in self.KINDS)
            r = random.uniform(0, total)
            acc = 0
            for letter, kind, color, w in self.KINDS:
                acc += w
                if r <= acc:
                    self.letter, self.kind, self.color = letter, kind, color
                    break
        self.p = pygame.math.Vector2(x, y)
        self.v = pygame.math.Vector2(random.uniform(-30, 30), random.uniform(-30, 30))
        self.life = 10
        self.sprite = make_powerup_sprite(letter, color)

    def update(self, dt):
        self.p += self.v * dt
        self.p = pygame.math.Vector2(*wrap(self.p.x, self.p.y))
        self.life -= dt

    def draw(self, s, t):
        pulse = 1 + 0.12 * math.sin(t * 6)
        rot = pygame.transform.scale(self.sprite, (int(56 * pulse), int(56 * pulse)))
        s.blit(rot, (self.p.x - rot.get_width() / 2, self.p.y - rot.get_height() / 2))
        if self.life < 3:  # blink when about to vanish
            if int(self.life * 6) % 2:
                pygame.draw.circle(s, (255, 255, 255), (int(self.p.x), int(self.p.y)), 24)

class SaucerBullet:
    def __init__(self, x, y, ang, speed=380):
        self.p = pygame.math.Vector2(x, y)
        self.v = pygame.math.Vector2(math.cos(ang), math.sin(ang)) * speed
        self.life = 2.5

    def update(self, dt):
        self.p += self.v * dt
        self.life -= dt

    def draw(self, s):
        g = make_glow(8, (255, 80, 200), 120)
        s.blit(g, (self.p.x - 8, self.p.y - 8), special_flags=pygame.BLEND_RGBA_ADD)
        pygame.draw.circle(s, (255, 170, 235), (int(self.p.x), int(self.p.y)), 3)

class Saucer:
    R = 34
    SCORE = 500

    def __init__(self):
        self.from_left = random.random() < 0.5
        self.p = pygame.math.Vector2(-80 if self.from_left else W + 80, random.uniform(80, H - 80))
        self.v = pygame.math.Vector2(1 if self.from_left else -1, 0) * random.uniform(90, 140)
        self.r = self.R  # for shield-deflection physics
        self.size = 3    # for shield-deflection physics
        self.t = 0
        self.fire_cd = random.uniform(0.8, 1.6)
        self.sprite = make_saucer_sprite()

    def update(self, dt, game):
        self.t += dt
        # always moving: steady forward across the screen
        self.p.x += self.v.x * dt
        # weaving: layered sines so it swerves even with no asteroids around
        vy = math.sin(self.t * 2.2) * 30 + math.sin(self.t * 0.9 + 1.3) * 50
        for ast in game.asteroids:
            d = (self.p - ast.p).length()
            clear = ast.r + 55
            if d < clear and d > 0.1:
                away = (self.p - ast.p).normalize()
                vy += away.y * (clear - d) * 3
        self.p.y += vy * dt
        self.p.y = clamp(self.p.y, 40, H - 40)
        # fire aimed shots while in transit
        self.fire_cd -= dt
        if self.fire_cd <= 0 and game.ship.alive:
            self.fire_cd = random.uniform(0.9, 1.6)
            ang = math.atan2(game.ship.p.y - self.p.y, game.ship.p.x - self.p.x)
            game.saucer_bullets.append(SaucerBullet(self.p.x, self.p.y, ang))

    @property
    def gone(self):
        return self.p.x < -120 or self.p.x > W + 120

    def draw(self, s, t):
        bob = 2 * math.sin(t * 5)
        g = make_glow(46, (255, 90, 190), int(50 + 25 * math.sin(t * 6)))
        s.blit(g, (self.p.x - 46, self.p.y - 46 + bob), special_flags=pygame.BLEND_RGBA_ADD)
        s.blit(self.sprite, (self.p.x - 48, self.p.y - 32 + bob))

class Mothership:
    R = 70
    BASE_HP = 25
    SCORE = 2000

    def __init__(self, hp=None):
        self.p = pygame.math.Vector2(W / 2, 110)
        self.hp = hp if hp is not None else self.BASE_HP
        self.max_hp = self.hp
        self.t = 0
        self.fire_cd = 1.2
        self.r = self.R  # for shield-deflection physics
        self.size = 3    # for shield-deflection physics
        self.sprite = make_mothership_sprite()

    def update(self, dt, game):
        self.t += dt
        self.p.x = W / 2 + math.sin(self.t * 0.4) * (W * 0.3)
        self.fire_cd -= dt
        if self.fire_cd <= 0 and game.ship.alive:
            self.fire_cd = 1.4
            base = math.atan2(game.ship.p.y - self.p.y, game.ship.p.x - self.p.x)
            for off in (-0.25, 0.0, 0.25):
                game.saucer_bullets.append(SaucerBullet(self.p.x, self.p.y, base + off, 300))

    def draw(self, s, t):
        pulse = 0.7 + 0.3 * math.sin(t * 4)
        g = make_glow(80, (255, 100, 80), int(50 * pulse))
        s.blit(g, (self.p.x - 80, self.p.y - 80), special_flags=pygame.BLEND_RGBA_ADD)
        s.blit(self.sprite, (self.p.x - 80, self.p.y - 60))
        w = int(120 * max(self.hp, 0) / self.max_hp)
        pygame.draw.rect(s, (80, 80, 100), (self.p.x - 60, self.p.y - 78, 120, 6))
        pygame.draw.rect(s, RED, (self.p.x - 60, self.p.y - 78, w, 6))

class FloatText:
    def __init__(self, x, y, text, color, size=22, life=0.9):
        self.p = pygame.math.Vector2(x, y)
        self.text, self.color, self.size, self.life, self.L = text, color, size, life, life
        self.font = pygame.font.Font(None, size)

    def update(self, dt):
        self.p.y -= 34 * dt
        self.life -= dt

    def draw(self, s):
        a = clamp(self.life / self.L, 0, 1)
        t = self.font.render(self.text, True, self.color)
        t.set_alpha(int(255 * a))
        s.blit(t, t.get_rect(center=(int(self.p.x), int(self.p.y))))

# ---------------------------------------------------------------- ship
class Ship:
    R = 20
    def __init__(self):
        self.reset(W / 2, H / 2)
        self.sprite = make_ship_sprite()
        self.trail = []

    def reset(self, x, y):
        self.p = pygame.math.Vector2(x, y)
        self.v = pygame.math.Vector2(0, 0)
        self.angle = -90
        self.alive = True
        self.shield = 2.5
        self.inv = 0
        self.trail = []

    def update(self, dt, keys):
        if not self.alive:
            return
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        up = keys[pygame.K_UP] or keys[pygame.K_w]
        down = keys[pygame.K_DOWN] or keys[pygame.K_s]
        rot_spd = 260
        if left: self.angle -= rot_spd * dt
        if right: self.angle += rot_spd * dt
        a = math.radians(self.angle)
        if up:
            self.v += pygame.math.Vector2(math.cos(a), math.sin(a)) * 420 * dt
        if down:
            self.v *= (1 - 2.2 * dt)
        self.v *= (1 - 0.55 * dt)
        self.v = clamp_mag(self.v, 520)
        self.p += self.v * dt
        self.p = pygame.math.Vector2(*wrap(self.p.x, self.p.y))
        self.trail.append((pygame.math.Vector2(self.p), self.angle))
        if len(self.trail) > 9: self.trail.pop(0)
        if self.shield > 0: self.shield -= dt
        if self.inv > 0: self.inv -= dt

    def draw(self, s, t):
        if not self.alive:
            return
        # afterburner trail
        for i, (tp, ta) in enumerate(self.trail):
            a = int(70 * i / len(self.trail))
            pygame.draw.circle(s, (120, 160, 255, a), (int(tp.x), int(tp.y)), 3)
        # blink while invulnerable
        if self.inv > 0 and int(t * 10) % 2:
            return
        rot = pygame.transform.rotate(self.sprite, -self.angle - 90)
        s.blit(rot, (self.p.x - rot.get_width() / 2, self.p.y - rot.get_height() / 2))
        # shield ring
        if self.shield > 0:
            a = int(120 + 90 * math.sin(t * 8))
            pygame.draw.circle(s, (120, 180, 255, a), (int(self.p.x), int(self.p.y)), 32, 2)
            g = make_glow(40, BLUE, 40)
            s.blit(g, (self.p.x - 40, self.p.y - 40), special_flags=pygame.BLEND_RGBA_ADD)

def clamp_mag(v, m):
    if v.length() > m:
        v = v.normalize() * m
    return v

# ---------------------------------------------------------------- game
class Game:
    def __init__(self, sfx, bg, fonts):
        self.sfx, self.bg, self.fonts = sfx, bg, fonts
        self.state = "menu"
        self.highscore = 0
        try:
            with open(HS_FILE) as f:
                self.highscore = int(f.read().strip() or 0)
        except Exception:
            pass
        self.stats = {"games": 0, "best_combo": 0, "saucers": 0, "bosses": 0}
        try:
            with open(STATS_FILE) as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=")
                        if k in self.stats:
                            self.stats[k] = int(v)
        except Exception:
            pass
        self.reset_run()

    def reset_run(self):
        self.score = 0
        self.lives = 3
        self.level = 1
        self.ship = Ship()
        self.bullets = []
        self.asteroids = []
        self.powerups = []
        self.saucer = None
        self.saucer_bullets = []
        self.saucer_t = random.uniform(10, 18)
        self.boss = None
        self.boss_count = 0
        self.weapon_tier = 1
        self.weapon_t = 0
        self.magnet_t = 0
        self.warp_t = 0.0
        self.flash = 0.0
        self.life_threshold = 10000
        self.life_step = 10000
        self.texts = []
        self.particles = Particles()
        self.time_scale = 1.0
        self.slow_t = 0
        self.effects = {"rapid": 0, "double": 0, "spread": 0, "shield": 0}
        self.fire_cd = 0
        self.shake = 0.0
        self.combo = 0
        self.combo_t = 0
        self.wave = 0
        self.spawn_queue = self._wave_size()
        self.spawn_t = 1.5
        self.pause = False
        self.gameover_t = 0
        self.respawn_t = 0

    def _wave_size(self):
        return 3 + self.level

    def start(self):
        self.reset_run()
        self.state = "play"
        self.stats["games"] += 1
        self.sfx.play("levelup")

    def spawn_asteroid(self):
        side = random.randint(0, 3)
        m = 60
        x, y = [(random.uniform(0, W), -m), (random.uniform(0, H), -m),
               (-m, random.uniform(0, H)), (W + m, random.uniform(0, H))][side]
        a = Asteroid(x, y, 3, 90 + self.level * 12)
        # aim roughly toward center
        a.v = (pygame.math.Vector2(W / 2, H / 2) - a.p).normalize() * a.v.length()
        self.asteroids.append(a)

    def add_score(self, amt, x, y):
        self.combo = self.combo + 1 if self.combo_t > 0 else 1
        self.combo_t = 2.0
        mult = min(self.combo, 8)
        pts = amt * mult
        self.score += pts
        self.texts.append(FloatText(x, y, f"+{pts}" + (f"  x{mult}" if mult > 1 else ""), YELLOW if mult > 1 else WHITE))
        if self.score > self.highscore:
            self.highscore = self.score
        self.stats["best_combo"] = max(self.stats["best_combo"], self.combo)
        self._check_life()

    def _check_life(self):
        # escalating milestones: 10k, then +20k, +30k, +40k, ...
        while self.score >= self.life_threshold and self.lives < 5:
            self.lives += 1
            self.life_step += 10000
            self.life_threshold += self.life_step
            self.sfx.play("levelup")
            self.texts.append(FloatText(self.ship.p.x, self.ship.p.y - 40, f"1UP - next at {self.life_threshold}", GREEN, 30, 1.5))

    def drop_powerup(self, x, y, kind=None):
        # cap on-screen power-ups so the field doesn't get crowded
        if len(self.powerups) < 3:
            self.powerups.append(PowerUp(x, y, kind=kind))

    def save_highscore(self):
        try:
            with open(HS_FILE, "w") as f:
                f.write(str(self.highscore))
        except Exception:
            pass

    def save_stats(self):
        try:
            with open(STATS_FILE, "w") as f:
                for k, v in self.stats.items():
                    f.write(f"{k}={v}\n")
        except Exception:
            pass

    def kill_saucer(self):
        s = self.saucer
        self.add_score(Saucer.SCORE, s.p.x, s.p.y)
        self.particles.burst(s.p.x, s.p.y, 60, (255, 120, 210), 300, 1.0)
        self.sfx.play("explosion_l")
        self.shake = max(self.shake, 12)
        # saucers drop a power-up (guaranteed nuke on high waves)
        self.drop_powerup(s.p.x, s.p.y, kind="nuke" if self.level >= 5 else None)
        self.stats["saucers"] += 1
        self.saucer = None
        self.saucer_t = random.uniform(12, 22)

    def kill_boss(self):
        b = self.boss
        self.add_score(Mothership.SCORE, b.p.x, b.p.y)
        self.particles.burst(b.p.x, b.p.y, 120, (255, 140, 80), 400, 1.4)
        self.particles.debris(b.p.x, b.p.y, 14, (255, 160, 120))
        self.sfx.play("nuke")
        self.shake = max(self.shake, 22)
        self.drop_powerup(b.p.x - 40, b.p.y)
        self.drop_powerup(b.p.x + 40, b.p.y)
        self.stats["bosses"] += 1
        self.boss = None

    def kill_asteroid(self, idx, big=False):
        ast = self.asteroids.pop(idx)
        self.add_score(Asteroid.SCORE[ast.size], ast.p.x, ast.p.y)
        n = {1: 14, 2: 26, 3: 44}[ast.size]
        self.particles.burst(ast.p.x, ast.p.y, n, (255, 170, 90), 160 + ast.size * 60, 0.7)
        self.sfx.play(["explosion_s", "explosion_m", "explosion_l"][ast.size - 1])
        self.shake = max(self.shake, {1: 3, 2: 6, 3: 10}[ast.size])
        for a in ast.split(random):
            self.asteroids.append(a)
        if random.random() < 0.08:
            self.drop_powerup(ast.p.x, ast.p.y)

    def damage_ship(self, source=None, idx=None):
        sh = self.ship
        if not sh.alive or sh.inv > 0:
            return
        if self.effects["shield"] > 0 or sh.shield > 0:
            if source is not None:
                # shielded contact counts as a hit on the asteroid: destroy it
                if idx is not None:
                    self.kill_asteroid(idx)
                # gentle deflection — greatly reduced impulse
                away = (sh.p - source.p).normalize()
                overlap = (source.r + Ship.R) - (sh.p - source.p).length()
                if overlap > 0:
                    sh.p += away * overlap
                impact = source.v.length()
                impulse = 40 + 0.15 * impact + 12 * (source.size - 1)
                impulse = min(impulse, 180)
                sh.v = away * impulse + source.v * 0.2
                n = int(12 + 5 * source.size)
                self.particles.burst(sh.p.x, sh.p.y, n, BLUE, 140 + impact * 0.3, 0.9)
                self.shake = max(self.shake, 2 + source.size)
            else:
                self.particles.burst(sh.p.x, sh.p.y, 40, BLUE, 260, 0.9)
                self.shake = max(self.shake, 8)
            self.sfx.play("shield")
            sh.inv = 0.3  # brief grace so the sound doesn't spam while overlapping
            return
        self.lives -= 1
        self.particles.burst(sh.p.x, sh.p.y, 70, (140, 190, 255), 320, 1.1)
        self.particles.debris(sh.p.x, sh.p.y, 10, (200, 220, 255))
        self.sfx.play("ship")
        self.shake = 16
        sh.alive = False
        if self.lives <= 0:
            self.state = "gameover"
            self.gameover_t = 0
            self.save_highscore()
            self.save_stats()
        else:
            self.respawn_t = 1.8

    def update(self, dt, keys):
        t = pygame.time.get_ticks() / 1000
        if self.state == "menu":
            self.bg.update(dt)
            self.sfx.saucer_off()
            return
        if self.state == "gameover":
            self.gameover_t += dt
            self.bg.update(dt)
            self.particles.update(dt)
            self.sfx.saucer_off()
            return
        if self.pause:
            return

        if self.slow_t > 0:
            self.slow_t -= dt
            self.time_scale = 0.45 if self.slow_t > 0 else 1.0
        wdt = dt * self.time_scale

        for k in ("rapid", "double", "spread", "shield"):
            self.effects[k] = max(0, self.effects[k] - dt)
        if self.weapon_t > 0:
            self.weapon_t -= dt
            if self.weapon_t <= 0:
                self.weapon_t = 0
                self.weapon_tier = 1
        if self.combo_t > 0:
            self.combo_t -= dt
            if self.combo_t <= 0:
                self.combo = 0
        self.warp_t = max(0.0, self.warp_t - dt)
        self.flash = max(0.0, self.flash - dt)

        self.bg.update(wdt, drift=self.ship.v.x / 520 if self.ship.alive else 0)

        # ship
        if self.ship.alive:
            self.ship.update(wdt, keys)
            thrusting = self.ship.v.length() > 60 and (keys[pygame.K_UP] or keys[pygame.K_w])
            if thrusting:
                self.sfx.thrust_on()
                a = math.radians(self.ship.angle)
                for _ in range(2):
                    self.particles.list.append({
                        "p": self.ship.p - pygame.math.Vector2(math.cos(a), math.sin(a)) * 22,
                        "v": pygame.math.Vector2(math.cos(a), math.sin(a)) * 120 + pygame.math.Vector2(random.uniform(-40, 40), random.uniform(-40, 40)),
                        "l": 0.35, "L": 0.35, "c": ORANGE, "s": 3,
                    })
            else:
                self.sfx.thrust_off()
            if keys[pygame.K_SPACE]:
                self.fire_cd -= wdt
                rate = 0.11 if self.effects["rapid"] > 0 else 0.22
                if self.fire_cd <= 0:
                    self.fire_cd = rate
                    self.fire()
        else:
            self.sfx.thrust_off()
            self.respawn_t -= dt
            if self.respawn_t <= 0 and self.lives > 0:
                pos = self.safe_position()
                self.ship.reset(*pos)

        # asteroids
        for i in range(len(self.asteroids)):
            self.asteroids[i].update(wdt)
        # bullets
        for b in self.bullets:
            b.update(wdt)
        self.bullets = [b for b in self.bullets if b.life > 0]
        for p in self.powerups:
            p.update(wdt)
        self.powerups = [p for p in self.powerups if p.life > 0]
        # magnet: pull nearby power-ups toward the ship
        if self.magnet_t > 0:
            self.magnet_t -= dt
            if self.ship.alive:
                for p in self.powerups:
                    d = p.p - self.ship.p
                    L = d.length()
                    if 1 < L < 280:
                        p.p -= d / L * min(L * 2.5, 320) * dt
        # saucer
        if self.saucer is None:
            self.saucer_t -= wdt
            if self.saucer_t <= 0:
                self.saucer = Saucer()
        else:
            self.saucer.update(wdt, self)
            if self.saucer.gone:
                self.saucer = None
                self.saucer_t = random.uniform(12, 22)
        # saucer warble follows the saucer's presence
        if self.saucer is not None:
            self.sfx.saucer_on()
        else:
            self.sfx.saucer_off()
        for b in self.saucer_bullets:
            b.update(wdt)
        self.saucer_bullets = [b for b in self.saucer_bullets if b.life > 0]

        # collisions: bullets vs asteroids
        for b in list(self.bullets):
            for i, ast in enumerate(self.asteroids):
                if (b.p - ast.p).length() < ast.r + 5:
                    self.bullets.remove(b)
                    self.kill_asteroid(i)
                    break
        # saucer/mothership bullets don't pass through asteroids: they count as a hit too
        for b in list(self.saucer_bullets):
            for i, ast in enumerate(self.asteroids):
                if (b.p - ast.p).length() < ast.r + 5:
                    self.saucer_bullets.remove(b)
                    self.kill_asteroid(i)
                    break

        # bullets vs saucer
        if self.saucer is not None:
            for b in list(self.bullets):
                if (b.p - self.saucer.p).length() < Saucer.R + 5:
                    self.bullets.remove(b)
                    self.kill_saucer()
                    break
        # ship vs asteroids
        sh = self.ship
        if sh.alive:
            for i, ast in enumerate(self.asteroids):
                if (sh.p - ast.p).length() < ast.r + Ship.R:
                    self.damage_ship(ast, i)
                    break
        # ship vs saucer
        if sh.alive and self.saucer is not None:
            if (sh.p - self.saucer.p).length() < Saucer.R + Ship.R:
                self.damage_ship(self.saucer)
        # near-miss bonus: flying close to an asteroid pays a little
        if sh.alive and sh.inv <= 0:
            for ast in self.asteroids:
                d = (sh.p - ast.p).length()
                if ast.nm_cd <= 0 and ast.r + Ship.R + 4 < d < ast.r + Ship.R + 30:
                    ast.nm_cd = 1.2
                    self.score += 5
                    if self.score > self.highscore:
                        self.highscore = self.score
                    self.texts.append(FloatText(ast.p.x, ast.p.y - ast.r, "+5", (170, 170, 200), 18, 0.5))
                    self.sfx.play("ui")
                    self._check_life()
        # ship vs saucer bullets
        if sh.alive:
            for b in list(self.saucer_bullets):
                if (b.p - sh.p).length() < Ship.R + 5:
                    self.saucer_bullets.remove(b)
                    self.damage_ship()
                    break
        # boss
        if self.boss is not None:
            self.boss.update(wdt, self)
            for b in list(self.bullets):
                if (b.p - self.boss.p).length() < Mothership.R + 5:
                    self.bullets.remove(b)
                    self.boss.hp -= 1
                    self.particles.burst(b.p.x, b.p.y, 6, (255, 140, 90), 120, 0.4)
                    self.sfx.play("ui")
                    if self.boss.hp <= 0:
                        self.kill_boss()
                    break
            if self.boss is not None and sh.alive and (sh.p - self.boss.p).length() < Mothership.R + Ship.R:
                self.damage_ship(self.boss)
        # ship vs powerups
        if sh.alive:
            for p in list(self.powerups):
                if (sh.p - p.p).length() < 40:
                    self.powerups.remove(p)
                    self.apply_powerup(p)

        # wave spawning
        if self.spawn_queue > 0:
            self.spawn_t -= wdt
            if self.spawn_t <= 0:
                self.spawn_t = random.uniform(0.4, 1.2)
                self.spawn_queue -= 1
                self.spawn_asteroid()
        elif len(self.asteroids) == 0:
            self.level += 1
            self.wave += 1
            self.spawn_queue = self._wave_size()
            self.spawn_t = 2.0
            self.texts.append(FloatText(W / 2, H / 3, f"WAVE {self.level}", CYAN, 48, 2.0))
            self.sfx.play("levelup")
            if self.level % 3 == 0:
                self.bg.regen()
                self.texts.append(FloatText(W / 2, H / 3 + 60, "SECTOR SHIFT", PURPLE, 36, 2.0))
                self.warp_t = 0.6
            if self.level % 5 == 0 and self.boss is None:
                # 25 hp base, +25 for every previous mothership defeated
                self.boss = Mothership(25 * (self.boss_count + 1))
                self.boss_count += 1
                self.texts.append(FloatText(W / 2, H / 3 + 110, "MOTHERSHIP", RED, 40, 2.5))

        self.particles.update(wdt)
        for ft in self.texts:
            ft.update(wdt)
        self.texts = [ft for ft in self.texts if ft.life > 0]
        self.shake = max(0, self.shake - 40 * dt)

    def safe_position(self, min_clear=90, tries=40):
        candidates = [(W / 2, H / 2)] + [(random.uniform(100, W - 100), random.uniform(100, H - 100)) for _ in range(tries)]
        for x, y in candidates:
            if all((pygame.math.Vector2(x, y) - a.p).length() > a.r + min_clear for a in self.asteroids):
                return x, y
        # field is packed; pick the spot with the most clearance
        best = max(candidates, key=lambda p: min((pygame.math.Vector2(*p) - a.p).length() for a in self.asteroids) or 9999)
        return best

    def fire(self):
        a = math.radians(self.ship.angle)
        def shoot(off):
            ang = a + off
            self.bullets.append(Bullet(self.ship.p.x + math.cos(ang) * 24, self.ship.p.y + math.sin(ang) * 24, ang))
        # weapon tier: 1-3 base shots (at tier 1, double/spread replace the base shot)
        base = self.weapon_tier
        has_double = self.effects["double"] > 0
        has_spread = self.effects["spread"] > 0
        if base > 1 or not (has_double or has_spread):
            for i in range(base):
                shoot((i - (base - 1) / 2) * 0.16)
        if has_double:
            # two parallel shots
            shoot(0.09); shoot(-0.09)
        if has_spread:
            # three-way fan
            shoot(0); shoot(0.3); shoot(-0.3)
        # kill-streak: laser pitch rises with the combo
        self.sfx.play(f"laser{min(max(self.combo - 1, 0), 4)}")

    def apply_powerup(self, p):
        names = {"rapid": "RAPID FIRE", "double": "DOUBLE SHOT", "spread": "SPREAD SHOT",
                "shield": "SHIELD", "slow": "TIME WARP", "nuke": "NUKE",
                "weapon": "WEAPON UP", "magnet": "MAGNET"}
        self.sfx.play("power")
        self.texts.append(FloatText(p.p.x, p.p.y, names[p.kind], p.color, 30, 1.2))
        if p.kind == "rapid": self.effects["rapid"] = 8
        elif p.kind == "double": self.effects["double"] = 10
        elif p.kind == "spread": self.effects["spread"] = 10
        elif p.kind == "shield": self.effects["shield"] = 12
        elif p.kind == "slow": self.slow_t = 6
        elif p.kind == "weapon":
            self.weapon_tier = min(3, self.weapon_tier + 1)
            self.weapon_t = 120
        elif p.kind == "magnet": self.magnet_t = 10
        elif p.kind == "nuke":
            self.sfx.play("nuke")
            self.shake = 24
            self.flash = 0.5
            for ast in list(self.asteroids):
                self.add_score(Asteroid.SCORE[ast.size], ast.p.x, ast.p.y)
                self.particles.burst(ast.p.x, ast.p.y, 30, (255, 120, 60), 260, 0.9)
            self.asteroids.clear()
            self.saucer_bullets.clear()
            self.particles.burst(self.ship.p.x, self.ship.p.y, 120, RED, 700, 1.4)

    # ---------------------------------------------------------------- draw
    def draw(self, s, t):
        self.bg.draw(s, t)
        ox = random.uniform(-1, 1) * self.shake
        oy = random.uniform(-1, 1) * self.shake
        if self.state == "menu":
            self.draw_menu(s, t)
            return
        world = pygame.Surface((W, H), pygame.SRCALPHA)
        for p in self.powerups:
            p.draw(world, t)
        for a in self.asteroids:
            a.draw(world)
        for b in self.bullets:
            b.draw(world)
        for b in self.saucer_bullets:
            b.draw(world)
        if self.saucer is not None:
            self.saucer.draw(world, t)
        if self.boss is not None:
            self.boss.draw(world, t)
        self.ship.draw(world, t)
        # active power-up shield (distinct from the short spawn shield)
        if self.effects["shield"] > 0 and self.ship.alive and not (self.effects["shield"] < 3 and int(t * 6) % 2):
            pulse = 0.75 + 0.25 * math.sin(t * 5)
            r = 38 + 3 * math.sin(t * 5)
            pygame.draw.circle(world, (100, 170, 255, int(180 * pulse)), (int(self.ship.p.x), int(self.ship.p.y)), int(r), 3)
            pygame.draw.circle(world, (160, 210, 255, int(90 * pulse)), (int(self.ship.p.x), int(self.ship.p.y)), int(r) + 5, 1)
            g = make_glow(52, BLUE, int(70 * pulse))
            world.blit(g, (self.ship.p.x - 52, self.ship.p.y - 52), special_flags=pygame.BLEND_RGBA_ADD)
        self.particles.draw(world)
        for ft in self.texts:
            ft.draw(world)
        s.blit(world, (ox, oy))
        if self.slow_t > 0:
            tint = pygame.Surface((W, H), pygame.SRCALPHA)
            tint.fill((120, 60, 255, 30))
            s.blit(tint, (0, 0))
        if self.flash > 0:
            fl = pygame.Surface((W, H), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(200 * self.flash / 0.5)))
            s.blit(fl, (0, 0))
        if self.warp_t > 0:
            k = self.warp_t / 0.6
            tint = pygame.Surface((W, H), pygame.SRCALPHA)
            tint.fill((120, 60, 255, int(70 * k)))
            s.blit(tint, (0, 0))
            for i in range(3):
                r = int((1 - k) * 900 + i * 60)
                pygame.draw.circle(s, (180, 120, 255, int(120 * k)), (W // 2, H // 2), r, 2)
        self.draw_hud(s, t)
        if self.pause:
            self.draw_center(s, "PAUSED", "press P to resume")
        if self.state == "gameover":
            self.draw_center(s, "GAME OVER", f"score {self.score}   best {self.highscore}" if self.gameover_t > 1.5 else "press ENTER to fly again")

    def draw_hud(self, s, t):
        f = self.fonts[28]
        s.blit(f.render(f"SCORE {self.score:06d}", True, WHITE), (20, 16))
        s.blit(f.render(f"BEST {self.highscore:06d}", True, (160, 160, 190)), (W - 190, 16))
        s.blit(self.fonts[20].render(f"WAVE {self.level}", True, (140, 140, 170)), (20, 48))
        # lives
        for i in range(self.lives):
            g = make_glow(10, (120, 180, 255), 60)
            s.blit(g, (24 + i * 44, 78), special_flags=pygame.BLEND_RGBA_ADD)
            pts = [(40 + i * 44, 74), (48 + i * 44, 94), (32 + i * 44, 94)]
            pygame.draw.polygon(s, (200, 220, 255), pts)
        # combo
        if self.combo > 1:
            c = lerp_color(YELLOW, RED, (min(self.combo, 8) - 1) / 7)
            s.blit(self.fonts[36].render(f"COMBO x{min(self.combo, 8)}", True, c), (W // 2 - 100, 18))
        if self.weapon_tier > 1:
            s.blit(self.fonts[20].render(f"WPN x{self.weapon_tier}", True, YELLOW), (20, 100))
        if self.lives < 5:
            s.blit(self.fonts[20].render(f"1UP - next at {self.life_threshold}", True, (140, 200, 160)), (20, 120))
        # effect bars
        y = H - 30
        def bar(col, frac):
            nonlocal y
            wbar = int(160 * max(0.0, min(1.0, frac)))
            pygame.draw.rect(s, col, (20, y, wbar, 6))
            pygame.draw.rect(s, (255, 255, 255), (20, y, wbar, 6), 1)
            y -= 14
        for name, col, dur in (("rapid", ORANGE, 8), ("double", GREEN, 10), ("spread", CYAN, 10)):
            if self.effects[name] > 0:
                bar(col, self.effects[name] / dur)
        if self.effects["shield"] > 0:
            bar(BLUE, self.effects["shield"] / 12)
        if self.slow_t > 0:
            bar(PURPLE, self.slow_t / 6)
        if self.magnet_t > 0:
            bar((255, 120, 240), self.magnet_t / 10)
        if self.weapon_t > 0:
            bar((255, 255, 255), self.weapon_t / 120)
        if self.sfx.muted:
            s.blit(self.fonts[20].render("MUTED (M)", True, (140, 140, 170)), (W - 150, H - 30))

    def draw_menu(self, s, t):
        # ambient drifting asteroids for flair
        for i in range(5):
            a = pygame.math.Vector2(((t * 40 * (i + 1)) % (W + 200)) - 100, (i * 137) % H)
            rot = pygame.transform.rotate(self._menu_asts[i][0], t * 30 * (i % 2 * 2 - 1))
            s.blit(rot, (a.x - rot.get_width() / 2, a.y - rot.get_height() / 2))
        # title
        title = self.fonts[96].render("ASTEROIDS 2026", True, WHITE)
        glow = make_glow(160, (100, 140, 255), 70)
        s.blit(glow, (W // 2 - 160, 130), special_flags=pygame.BLEND_RGBA_ADD)
        s.blit(title, title.get_rect(center=(W // 2, 190)))
        sub = self.fonts[28].render("a classic, updated for gamers in 2026 — 100% procedural", True, (150, 150, 200))
        s.blit(sub, sub.get_rect(center=(W // 2, 250)))
        if self.highscore:
            hs = self.fonts[30].render(f"best: {self.highscore:06d}", True, YELLOW)
            s.blit(hs, hs.get_rect(center=(W // 2, 300)))
        pulse = 0.6 + 0.4 * math.sin(t * 3)
        go = self.fonts[44].render("PRESS  ENTER  TO  LAUNCH", True, lerp_color((100, 100, 140), WHITE, pulse))
        s.blit(go, go.get_rect(center=(W // 2, 400)))
        lines = ["arrows / WASD  steer & thrust", "space  fire", "P  pause   M  mute   F  fullscreen   - / +  volume   ESC  menu"]
        for i, ln in enumerate(lines):
            s.blit(self.fonts[24].render(ln, True, (130, 130, 165)), self.fonts[24].render(ln, True, (0, 0, 0)).get_rect(center=(W // 2, 480 + i * 34)))
        pk = self.fonts[24].render("power-ups:  R rapid   D double   S spread   B shield   T time-warp   N nuke   W weapon   M magnet", True, (110, 110, 150))
        s.blit(pk, pk.get_rect(center=(W // 2, 620)))
        st = self.fonts[20].render(f"games {self.stats['games']}   best combo x{self.stats['best_combo']}   saucers {self.stats['saucers']}   bosses {self.stats['bosses']}", True, (110, 110, 150))
        s.blit(st, st.get_rect(center=(W // 2, 660)))

    def draw_center(self, s, big, small):
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((0, 0, 10, 140))
        s.blit(ov, (0, 0))
        b = self.fonts[72].render(big, True, WHITE)
        s.blit(b, b.get_rect(center=(W // 2, H // 2 - 30)))
        x = self.fonts[30].render(small, True, (170, 170, 210))
        s.blit(x, x.get_rect(center=(W // 2, H // 2 + 40)))

# ---------------------------------------------------------------- main
def main():
    if "--selftest" in sys.argv:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Asteroids 2026")
    clock = pygame.time.Clock()
    sfx = Sfx()
    bg = Background()
    fonts = {
        20: pygame.font.Font(None, 20), 24: pygame.font.Font(None, 24),
        28: pygame.font.Font(None, 28), 30: pygame.font.Font(None, 30),
        36: pygame.font.Font(None, 36), 44: pygame.font.Font(None, 44),
        72: pygame.font.Font(None, 72), 96: pygame.font.Font(None, 96),
    }
    game = Game(sfx, bg, fonts)
    # menu ambient asteroids
    game._menu_asts = [(make_asteroid_sprite(r, i * 7 + 3), r) for i, r in enumerate([40, 26, 18, 34, 22])]
    selftest = "--selftest" in sys.argv
    frames = 0
    while True:
        dt = min(clock.tick(FPS) / 1000, 0.05)
        keys = pygame.key.get_pressed()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                game.save_highscore()
                game.save_stats()
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_m:
                    sfx.toggle_mute()
                if ev.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()
                if ev.key == pygame.K_PLUS or ev.key == pygame.K_EQUALS:
                    sfx.master = min(1.0, sfx.master + 0.1)
                    game.texts.append(FloatText(W / 2, H / 2, f"VOL {sfx.master:.1f}", WHITE, 30, 0.8))
                if ev.key == pygame.K_MINUS:
                    sfx.master = max(0.0, sfx.master - 0.1)
                    game.texts.append(FloatText(W / 2, H / 2, f"VOL {sfx.master:.1f}", WHITE, 30, 0.8))
                if ev.key == pygame.K_p and game.state == "play":
                    game.pause = not game.pause
                if ev.key == pygame.K_ESCAPE:
                    if game.state == "play":
                        game.state = "menu"
                        sfx.thrust_off()
                        sfx.saucer_off()
                    else:
                        game.save_highscore()
                        game.save_stats()
                        return
                if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if game.state in ("menu", "gameover") and (game.state == "menu" or game.gameover_t > 1.0):
                        game.start()
                if ev.key == pygame.K_SPACE and game.state == "menu":
                    game.start()
        game.update(dt, keys)
        game.draw(screen, pygame.time.get_ticks() / 1000)
        pygame.display.flip()
        frames += 1
        if selftest and frames >= 300:
            game.save_highscore()
            game.save_stats()
            print("SELFTEST OK")
            return

if __name__ == "__main__":
    main()
