#!/usr/bin/env python3
"""
Autonomous OLED-style robot eyes for Termux/Termux:Float.
This version uses continuous pose interpolation, internal emotional drives,
Portuguese-BR speech, and small persisted habits instead of expression hotkeys.

v2 — Sensor Integration:
  - Proximity  (ltr569_ps)   → reacts when someone approaches
  - Ambient light (ltr569_als) → dims/brightens, sleepy in the dark
  - Accelerometer (lsm6dsv_acc) → reacts to device movement/shake
  - Motoglance                  → wakes up when user raises device
"""

from __future__ import annotations

import curses
import json
import math
import os
import random
import shutil
import subprocess
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

FPS = 24
FRAME_W = 58
FRAME_H = 17
ROOT = Path(__file__).resolve().parent
STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "py-eye"
STATE_FILE = STATE_DIR / "brain.json"
SOUND_DIR = ROOT / "sound" / "generated"
LEGACY_SOUND = ROOT / "sound" / "robot-notif.wav"

BEHAVIORS = [
    "calm", "observe", "curious", "happy", "giggle", "surprised",
    "annoyed", "sleepy", "sleep", "love", "confused", "dizzy",
    "bored", "talking", "shy", "smug",
]

PT_BR_DIALOG = {
    "curious": ["Humm... o que será isso?", "Péra aí... tô pensando.", "Curioso isso, viu."],
    "happy": ["Aí sim, gostei.", "Tô de bom humor hoje.", "Isso ficou legal."],
    "giggle": ["He he he... essa foi boa.", "Ai, ai... quase travei de rir."],
    "surprised": ["Opa! Essa eu não esperava.", "Eita... que susto."],
    "annoyed": ["Ei... calma aí.", "Hum... não gostei muito disso."],
    "sleepy": ["Tô ficando com soninho.", "Minha bateria emocional tá baixa."],
    "sleep": ["Vou descansar um pouquinho.", "Modo soneca ativado."],
    "love": ["Gostei de você por perto.", "Sinal quentinho detectado."],
    "confused": ["Péra... deixa eu entender.", "Acho que misturei os pensamentos."],
    "dizzy": ["Uou... deu uma tonturinha.", "Meu sensor ficou girando."],
    "bored": ["Tá tudo quieto demais.", "Cadê alguma coisa interessante?"],
    "talking": ["Oi. Eu tô acordado.", "Eu tô te observando daqui."],
    "shy": ["Oi... fiquei sem jeito agora.", "Tô meio tímido."],
    "smug": ["Eu sabia.", "Tá vendo? Eu calculei certinho."],
}


def clamp(value, low, high):
    return max(low, min(high, value))


def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def choice_weighted(rng, scores):
    names = list(scores)
    values = np.array([scores[name] for name in names], dtype=float)
    values = values - np.max(values)
    exp = np.exp(values * 2.2)
    probs = exp / np.sum(exp)
    return str(rng.choice(names, p=probs))


# ─── SENSOR ENGINE ────────────────────────────────────────────────────────────

class SensorEngine:
    """
    Reads Termux sensors in a background thread.
    Provides non-blocking access to proximity, light, accelerometer and Motoglance.
    """
    POLL_INTERVAL = 1.2        # seconds between termux-sensor calls
    MOTION_THRESHOLD = 3.5    # m/s² delta to consider "shaking"
    PROX_NEAR_THRESHOLD = 6   # raw value ≤ this → someone near
    LIGHT_DIM_THRESHOLD = 5   # lux ≤ this → dark environment
    LIGHT_BRIGHT_THRESHOLD = 80  # lux ≥ this → very bright

    def __init__(self):
        self._lock = threading.Lock()
        self._proximity_near = False   # True  → object/person detected
        self._light_lux = 50.0         # ambient light in lux
        self._accel = [0.0, 0.0, 9.8]  # [x, y, z] m/s²
        self._prev_accel = [0.0, 0.0, 9.8]
        self._motion_mag = 0.0         # current shake magnitude
        self._glance = False           # Motoglance fired recently
        self._glance_ts = 0.0
        self._running = False
        self._thread = None
        self._termux_sensor = shutil.which("termux-sensor")

    def start(self):
        if not self._termux_sensor:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    # ── public accessors (thread-safe) ──────────────────────────────────────

    @property
    def proximity_near(self) -> bool:
        with self._lock:
            return self._proximity_near

    @property
    def light_lux(self) -> float:
        with self._lock:
            return self._light_lux

    @property
    def motion_magnitude(self) -> float:
        with self._lock:
            return self._motion_mag

    @property
    def glance_active(self) -> bool:
        """True for ~3 s after Motoglance fires."""
        with self._lock:
            return (time.monotonic() - self._glance_ts) < 3.0 and self._glance

    # ── sensor categories ────────────────────────────────────────────────────

    @property
    def is_dark(self) -> bool:
        return self.light_lux <= self.LIGHT_DIM_THRESHOLD

    @property
    def is_very_bright(self) -> bool:
        return self.light_lux >= self.LIGHT_BRIGHT_THRESHOLD

    @property
    def is_shaking(self) -> bool:
        return self.motion_magnitude > self.MOTION_THRESHOLD

    # ── background polling ───────────────────────────────────────────────────

    def _read_sensor(self, sensor_name: str, n: int = 1) -> dict | None:
        try:
            result = subprocess.run(
                [self._termux_sensor, "-s", sensor_name, "-n", str(n)],
                capture_output=True, text=True, timeout=4.0
            )
            return json.loads(result.stdout)
        except Exception:
            return None

    def _loop(self):
        while self._running:
            try:
                self._poll_proximity()
                self._poll_light()
                self._poll_accel()
                self._poll_glance()
            except Exception:
                pass
            time.sleep(self.POLL_INTERVAL)

    def _poll_proximity(self):
        data = self._read_sensor("ltr569_ps", 1)
        if not data:
            return
        # termux-sensor returns {"values": [[val]]} or similar
        val = self._extract_first_value(data)
        if val is not None:
            with self._lock:
                self._proximity_near = val <= self.PROX_NEAR_THRESHOLD

    def _poll_light(self):
        data = self._read_sensor("ltr569_als", 1)
        if not data:
            return
        val = self._extract_first_value(data)
        if val is not None:
            with self._lock:
                # Smooth the light reading to avoid flicker
                self._light_lux = lerp(self._light_lux, float(val), 0.4)

    def _poll_accel(self):
        data = self._read_sensor("lsm6dsv_acc", 1)
        if not data:
            return
        vals = self._extract_vector(data)
        if vals and len(vals) >= 3:
            with self._lock:
                prev = list(self._accel)
                self._accel = vals[:3]
                delta = [self._accel[i] - prev[i] for i in range(3)]
                self._motion_mag = math.sqrt(sum(d * d for d in delta))

    def _poll_glance(self):
        data = self._read_sensor("Motoglance", 1)
        if not data:
            return
        val = self._extract_first_value(data)
        if val is not None and val > 0:
            with self._lock:
                self._glance = True
                self._glance_ts = time.monotonic()

    def _extract_first_value(self, data: dict) -> float | None:
        """Parse termux-sensor JSON: {sensor_name: {values: [[v,...]]}}"""
        try:
            for sensor_key in data:
                sensor_data = data[sensor_key]
                if isinstance(sensor_data, dict):
                    values = sensor_data.get("values", [])
                    if values:
                        first = values[0]
                        if isinstance(first, list):
                            return float(first[0])
                        return float(first)
            return None
        except (KeyError, IndexError, TypeError, ValueError):
            return None

    def _extract_vector(self, data: dict) -> list[float] | None:
        """Parse multi-axis sensor data → list of floats."""
        try:
            for sensor_key in data:
                sensor_data = data[sensor_key]
                if isinstance(sensor_data, dict):
                    values = sensor_data.get("values", [])
                    if values:
                        first = values[0]
                        if isinstance(first, list):
                            return [float(v) for v in first]
                        return [float(first)]
            return None
        except (KeyError, IndexError, TypeError, ValueError):
            return None


# ─── HABIT BRAIN ──────────────────────────────────────────────────────────────

class HabitBrain:
    def __init__(self):
        self.rng = np.random.default_rng()
        self.habits = defaultdict(float)
        self.counts = defaultdict(int)
        self.personality = {
            "curiosity": 0.58,
            "playfulness": 0.52,
            "patience": 0.55,
            "affection": 0.42,
            "talkative": 0.38,
        }
        self.drives = {
            "energy": 0.82,
            "mood": 0.12,
            "curiosity": 0.55,
            "social": 0.35,
            "irritation": 0.12,
        }
        self.recent = deque(maxlen=10)
        self.last_behavior = None
        self.last_context = None
        self.last_start = time.monotonic()
        self.load()

    def load(self):
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text())
        except (OSError, json.JSONDecodeError):
            return
        for key, value in data.get("habits", {}).items():
            if isinstance(value, (int, float)):
                self.habits[str(key)] = float(value)
        for key, value in data.get("counts", {}).items():
            if isinstance(value, (int, float)):
                self.counts[str(key)] = int(value)
        self.personality.update({k: clamp(float(v), 0.05, 0.95) for k, v in data.get("personality", {}).items() if k in self.personality})
        self.drives.update({k: clamp(float(v), -1.0 if k == "mood" else 0.0, 1.0) for k, v in data.get("drives", {}).items() if k in self.drives})

    def save(self):
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "habits": dict(self.habits),
            "counts": dict(self.counts),
            "personality": self.personality,
            "drives": self.drives,
            "recent": list(self.recent),
            "updated_at": time.time(),
        }
        STATE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))

    def context(self, idle):
        hour = time.localtime().tm_hour
        day = "madrugada" if hour < 5 else "manha" if hour < 12 else "tarde" if hour < 19 else "noite"
        idle_band = "ativo" if idle < 8 else "calmo" if idle < 40 else "sozinho" if idle < 120 else "abandonado"
        energy = "baixa" if self.drives["energy"] < 0.35 else "media" if self.drives["energy"] < 0.68 else "alta"
        mood = "mal" if self.drives["mood"] < -0.25 else "bem" if self.drives["mood"] > 0.25 else "neutro"
        return f"{day}:{idle_band}:{energy}:{mood}"

    def update_drives(self, dt, idle, stimulated, sensors: SensorEngine | None = None):
        d = self.drives
        p = self.personality
        d["energy"] = clamp(d["energy"] - dt * (0.004 + 0.004 * p["playfulness"]), 0.0, 1.0)
        d["curiosity"] = clamp(d["curiosity"] + dt * 0.010, 0.0, 1.0)
        d["social"] = clamp(d["social"] + dt * (0.006 if idle > 15 else -0.010), 0.0, 1.0)
        d["irritation"] = clamp(d["irritation"] + dt * (0.003 if idle > 90 else -0.006), 0.0, 1.0)
        d["mood"] = clamp(d["mood"] + dt * (0.004 if d["energy"] > 0.45 else -0.006), -1.0, 1.0)
        if stimulated:
            d["social"] = clamp(d["social"] - 0.18, 0.0, 1.0)
            d["curiosity"] = clamp(d["curiosity"] + 0.12, 0.0, 1.0)
            d["mood"] = clamp(d["mood"] + 0.10, -1.0, 1.0)
            d["irritation"] = clamp(d["irritation"] - 0.10, 0.0, 1.0)

        # ── Sensor-driven drive modulation ───────────────────────────────────
        if sensors:
            # Proximity: someone near → social drive drops (satisfied), mood up
            if sensors.proximity_near:
                d["social"] = clamp(d["social"] - dt * 0.08, 0.0, 1.0)
                d["mood"] = clamp(d["mood"] + dt * 0.06, -1.0, 1.0)
                d["irritation"] = clamp(d["irritation"] - dt * 0.04, 0.0, 1.0)

            # Dark environment → sleepiness increases, energy drains faster
            if sensors.is_dark:
                d["energy"] = clamp(d["energy"] - dt * 0.006, 0.0, 1.0)

            # Very bright → curiosity boost, mood slightly positive
            if sensors.is_very_bright:
                d["curiosity"] = clamp(d["curiosity"] + dt * 0.008, 0.0, 1.0)
                d["mood"] = clamp(d["mood"] + dt * 0.003, -1.0, 1.0)

            # Shake → surprise/dizzy, irritation spike
            if sensors.is_shaking:
                d["curiosity"] = clamp(d["curiosity"] + 0.08, 0.0, 1.0)
                d["irritation"] = clamp(d["irritation"] + 0.06, 0.0, 1.0)

            # Motoglance → woken up, social + mood boost
            if sensors.glance_active:
                d["social"] = clamp(d["social"] + dt * 0.12, 0.0, 1.0)
                d["energy"] = clamp(d["energy"] + dt * 0.05, 0.0, 1.0)
                d["mood"] = clamp(d["mood"] + dt * 0.04, -1.0, 1.0)

    def close_behavior(self, interrupted=False):
        if not self.last_behavior or not self.last_context:
            return
        elapsed = time.monotonic() - self.last_start
        key = f"{self.last_context}|{self.last_behavior}"
        reward = 0.02
        if elapsed > 2.0:
            reward += 0.08
        if self.last_behavior not in list(self.recent)[-4:]:
            reward += 0.05
        if interrupted:
            reward -= 0.12
        if self.last_behavior in ("sleep", "sleepy") and self.drives["energy"] < 0.4:
            reward += 0.12
        if self.last_behavior in ("curious", "observe") and self.drives["curiosity"] > 0.65:
            reward += 0.10
        if self.last_behavior in ("happy", "giggle", "love") and self.drives["mood"] > 0.1:
            reward += 0.10
        self.counts[key] += 1
        alpha = 1.0 / math.sqrt(self.counts[key])
        self.habits[key] += alpha * (reward - self.habits[key])

    def choose_behavior(self, idle, stimulated=False, sensors: SensorEngine | None = None):
        self.close_behavior(False)
        ctx = self.context(idle)
        d = self.drives
        p = self.personality
        hour = time.localtime().tm_hour
        night = hour >= 23 or hour < 6
        scores = {name: 0.0 for name in BEHAVIORS}

        scores["calm"] += 0.30 + d["energy"] * 0.18 + p["patience"] * 0.12
        scores["observe"] += d["curiosity"] * 0.55 + p["curiosity"] * 0.22
        scores["curious"] += d["curiosity"] * 0.48 + stimulated * 0.35
        scores["talking"] += d["social"] * 0.36 + p["talkative"] * 0.25 + stimulated * 0.16
        scores["happy"] += max(0, d["mood"]) * 0.42 + p["playfulness"] * 0.20 + stimulated * 0.20
        scores["giggle"] += max(0, d["mood"]) * 0.26 + p["playfulness"] * 0.30
        scores["love"] += p["affection"] * 0.35 + stimulated * 0.18 + max(0, d["mood"]) * 0.18
        scores["confused"] += d["curiosity"] * 0.20 + random.random() * 0.08
        scores["surprised"] += stimulated * 0.22 + random.random() * 0.04
        scores["bored"] += max(0, idle - 35) / 150.0 + (1.0 - d["curiosity"]) * 0.12
        scores["sleepy"] += (1.0 - d["energy"]) * 0.55 + (0.20 if night else 0.0)
        scores["sleep"] += (1.0 - d["energy"]) * 0.70 + (0.35 if night and idle > 45 else 0.0)
        scores["annoyed"] += d["irritation"] * 0.50 + max(0, -d["mood"]) * 0.22
        scores["smug"] += max(0, d["mood"]) * 0.18 + p["patience"] * 0.08
        scores["shy"] += p["affection"] * 0.16 + stimulated * 0.10
        scores["dizzy"] += 0.02 + random.random() * 0.025

        # ── Sensor-driven behavior biases ─────────────────────────────────────
        if sensors:
            if sensors.proximity_near:
                scores["love"] += 0.30
                scores["shy"] += 0.18
                scores["talking"] += 0.22
                scores["surprised"] += 0.10

            if sensors.is_dark:
                scores["sleepy"] += 0.35
                scores["sleep"] += 0.25
                scores["bored"] += 0.12
                scores["calm"] += 0.10

            if sensors.is_very_bright:
                scores["curious"] += 0.18
                scores["observe"] += 0.15
                scores["happy"] += 0.10

            if sensors.is_shaking:
                scores["surprised"] += 0.40
                scores["dizzy"] += 0.30
                scores["annoyed"] += 0.18

            if sensors.glance_active:
                scores["talking"] += 0.28
                scores["curious"] += 0.20
                scores["happy"] += 0.15
                scores["sleep"] -= 0.50   # wake up!
                scores["sleepy"] -= 0.30

        for name in BEHAVIORS:
            scores[name] += self.habits[f"{ctx}|{name}"] * 0.45
            scores[name] -= list(self.recent).count(name) * 0.16
        if self.last_behavior:
            scores[self.last_behavior] -= 0.30
        if d["energy"] < 0.24:
            for name in ("giggle", "dizzy", "surprised", "talking"):
                scores[name] -= 0.30
        if d["irritation"] > 0.65:
            scores["annoyed"] += 0.28
            scores["happy"] -= 0.18
            scores["giggle"] -= 0.22

        behavior = choice_weighted(self.rng, scores)
        self.last_context = ctx
        self.last_behavior = behavior
        self.last_start = time.monotonic()
        self.recent.append(behavior)
        self.apply_behavior_effects(behavior)
        return behavior

    def apply_behavior_effects(self, behavior):
        d = self.drives
        if behavior in ("observe", "curious", "confused"):
            d["curiosity"] = clamp(d["curiosity"] - 0.18, 0.0, 1.0)
            self.personality["curiosity"] = clamp(self.personality["curiosity"] + 0.003, 0.05, 0.95)
        if behavior in ("happy", "giggle", "love"):
            d["mood"] = clamp(d["mood"] + 0.08, -1.0, 1.0)
            self.personality["playfulness"] = clamp(self.personality["playfulness"] + 0.003, 0.05, 0.95)
        if behavior == "sleep":
            d["energy"] = clamp(d["energy"] + 0.18, 0.0, 1.0)
            d["irritation"] = clamp(d["irritation"] - 0.12, 0.0, 1.0)
        elif behavior in ("giggle", "dizzy", "talking"):
            d["energy"] = clamp(d["energy"] - 0.05, 0.0, 1.0)
        if behavior == "annoyed":
            d["irritation"] = clamp(d["irritation"] - 0.16, 0.0, 1.0)
            d["mood"] = clamp(d["mood"] - 0.04, -1.0, 1.0)
        if behavior == "talking":
            d["social"] = clamp(d["social"] - 0.25, 0.0, 1.0)
            self.personality["talkative"] = clamp(self.personality["talkative"] + 0.003, 0.05, 0.95)


# ─── AUDIO ENGINE ─────────────────────────────────────────────────────────────

class AudioEngine:
    def __init__(self):
        self.play = shutil.which("play-audio")
        self.tts = shutil.which("termux-tts-speak")
        self.last_sound = 0.0
        self.last_talk = 0.0

    def maybe_sound(self, behavior):
        now = time.monotonic()
        if now - self.last_sound < 0.6:
            return
        name = "angry" if behavior == "annoyed" else behavior
        candidates = [SOUND_DIR / f"{name}.wav", LEGACY_SOUND]
        sound = next((p for p in candidates if p.exists()), None)
        if not sound or not self.play:
            return
        self.last_sound = now
        try:
            subprocess.Popen([self.play, str(sound)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def maybe_talk(self, behavior, talkative, reason_level=0.0):
        if behavior not in PT_BR_DIALOG or not self.tts:
            return
        now = time.monotonic()
        cooldown = 18.0 - talkative * 7.0
        chance = 0.06 + talkative * 0.10 + reason_level * 0.10
        if now - self.last_talk < cooldown or random.random() > chance:
            return
        self.last_talk = now
        text = random.choice(PT_BR_DIALOG[behavior])
        cmd = [
            self.tts,
            "-l", "pt",
            "-n", "BR",
            "-p", "0.92",
            "-r", "0.86",
            "-s", "MUSIC",
            text,
        ]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass


# ─── EYE APP ──────────────────────────────────────────────────────────────────

class EyeApp:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.running = True
        self.brain = HabitBrain()
        self.audio = AudioEngine()
        self.sensors = SensorEngine()
        self.last_input = time.monotonic()
        self.last_frame = time.monotonic()
        self.last_save = time.monotonic()
        self.behavior = "calm"
        self.behavior_start = time.monotonic()
        self.behavior_duration = 4.0
        self.next_blink = time.monotonic() + random.uniform(2.5, 6.0)
        self.blink_end = 0.0
        self.stimulated = False
        self.color = 1
        self.pose = self.base_pose()
        self.target = dict(self.pose)

        # Sensor state tracking (to detect transitions, not just levels)
        self._was_near = False
        self._was_shaking = False
        self._was_glancing = False

    def base_pose(self):
        return {
            "lx": 11.0, "ly": 5.0, "lw": 12.0, "lh": 7.0,
            "rx": 35.0, "ry": 5.0, "rw": 12.0, "rh": 7.0,
            "squash": 0.0, "cut_l": 0.0, "cut_r": 0.0,
            "mouth": 0.0, "tilt": 0.0, "shake": 0.0,
        }

    def setup(self):
        try:
            curses.use_default_colors()
        except curses.error:
            pass
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        self.stdscr.nodelay(True)
        self.stdscr.timeout(0)
        try:
            if curses.has_colors():
                curses.init_pair(self.color, curses.COLOR_CYAN, -1)
            else:
                self.color = 0
        except (curses.error, ValueError):
            self.color = 0

    def run(self):
        self.setup()
        self.sensors.start()
        frame_time = 1.0 / FPS
        try:
            while self.running:
                frame_start = time.monotonic()
                dt = min(0.10, frame_start - self.last_frame)
                self.last_frame = frame_start
                self.handle_input()
                self._check_sensor_events()
                self.update(frame_start, dt)
                self.draw(frame_start, dt)
                if frame_start - self.last_save > 20:
                    self.brain.save()
                    self.last_save = frame_start
                elapsed = time.monotonic() - frame_start
                time.sleep(max(0.0, frame_time - elapsed))
        finally:
            self.sensors.stop()
            self.brain.close_behavior(True)
            self.brain.save()

    def _check_sensor_events(self):
        """Detect rising edges on sensor states to trigger one-shot stimuli."""
        near = self.sensors.proximity_near
        shaking = self.sensors.is_shaking
        glancing = self.sensors.glance_active

        # Proximity: someone just appeared → stimulate (like a keypress)
        if near and not self._was_near:
            self.last_input = time.monotonic()
            self.stimulated = True
        self._was_near = near

        # Shake: sudden motion → stimulate
        if shaking and not self._was_shaking:
            self.stimulated = True
        self._was_shaking = shaking

        # Motoglance: device raised → stimulate (wake from sleep)
        if glancing and not self._was_glancing:
            self.last_input = time.monotonic()
            self.stimulated = True
        self._was_glancing = glancing

    def handle_input(self):
        while True:
            key = self.stdscr.getch()
            if key == curses.ERR:
                break
            if key in (ord("q"), ord("Q"), 27):
                self.running = False
            elif key == curses.KEY_RESIZE:
                self.stdscr.erase()
            else:
                self.last_input = time.monotonic()
                self.stimulated = True

    def update(self, now, dt):
        idle = now - self.last_input
        self.brain.update_drives(dt, idle, self.stimulated, self.sensors)
        if now >= self.next_blink and self.behavior not in ("sleep", "sleepy", "giggle", "dizzy"):
            self.blink_end = now + random.uniform(0.11, 0.18)
            self.next_blink = now + random.uniform(2.2, 7.0)
        if now >= self.behavior_start + self.behavior_duration:
            self.choose_next(now, idle)
        self.stimulated = False

    def choose_next(self, now, idle):
        behavior = self.brain.choose_behavior(idle, self.stimulated, self.sensors)
        self.behavior = behavior
        self.behavior_start = now
        self.behavior_duration = behavior_duration(behavior, self.brain.drives)
        if behavior not in ("calm", "observe", "sleep"):
            self.audio.maybe_sound(behavior)
        reason_level = max(self.brain.drives["social"], self.brain.drives["curiosity"], abs(self.brain.drives["mood"]))
        self.audio.maybe_talk(behavior, self.brain.personality["talkative"], reason_level)

    def progress(self, now):
        return clamp((now - self.behavior_start) / max(0.001, self.behavior_duration), 0.0, 1.0)

    def update_target_pose(self, now):
        p = self.progress(now)
        phase = now - self.behavior_start
        target = self.pose_for(self.behavior, p, phase)
        if now < self.blink_end:
            target["lh"] = min(target["lh"], 1.2)
            target["rh"] = min(target["rh"], 1.2)
            target["squash"] = 0.0
        self.target = target

    def pose_for(self, behavior, p, phase):
        t = smoothstep(min(1.0, p * 1.8))
        pose = self.base_pose()
        breathe = math.sin(phase * 2.0) * 0.35
        pose["ly"] += breathe
        pose["ry"] += breathe

        if behavior == "calm":
            pose["lh"] = 6.5 + math.sin(phase * 1.4) * 0.4
            pose["rh"] = pose["lh"]
        elif behavior == "observe":
            offset = math.sin(phase * 1.1) * 6.0
            pose["lx"] += offset
            pose["rx"] += offset
            pose["lh"] = 7.2
            pose["rh"] = 7.2
        elif behavior == "curious":
            pose["lx"] -= 1.2
            pose["rx"] += 1.0
            pose["ly"] -= 0.7 * t
            pose["rh"] = 5.4
            pose["rw"] = 13.0
            pose["mouth"] = 1.0
        elif behavior == "happy":
            pose["lh"] = 2.2
            pose["rh"] = 2.2
            pose["ly"] += 2.0 - math.sin(phase * 5.5) * 0.5
            pose["ry"] = pose["ly"]
            pose["mouth"] = 2.0
        elif behavior == "giggle":
            wiggle = math.sin(phase * 18.0) * 1.1
            pose["lx"] += wiggle
            pose["rx"] += wiggle
            pose["lh"] = 1.6
            pose["rh"] = 1.6
            pose["ly"] += 2.0
            pose["ry"] += 2.0
            pose["mouth"] = 3.0
        elif behavior == "surprised":
            pulse = math.sin(phase * 9.0) * 0.8
            pose["lx"] -= 1.0
            pose["rx"] += 1.0
            pose["lw"] = 13.8 + pulse
            pose["rw"] = 13.8 + pulse
            pose["lh"] = 9.2 + pulse
            pose["rh"] = 9.2 + pulse
            pose["ly"] -= 1.0
            pose["ry"] -= 1.0
            pose["mouth"] = 4.0
        elif behavior == "annoyed":
            shake = math.sin(phase * 20.0) * 0.7
            pose["lx"] += shake
            pose["rx"] += shake
            pose["lh"] = 5.2
            pose["rh"] = 5.2
            pose["cut_l"] = 5.0
            pose["cut_r"] = 5.0
            pose["mouth"] = 5.0
        elif behavior == "sleepy":
            pose["lh"] = 2.4 + math.sin(phase * 2.0) * 0.3
            pose["rh"] = pose["lh"]
            pose["ly"] += 2.0
            pose["ry"] += 2.0
            pose["mouth"] = 6.0
        elif behavior == "sleep":
            pose["lh"] = 1.0
            pose["rh"] = 1.0
            pose["ly"] += 3.0
            pose["ry"] += 3.0
            pose["mouth"] = 7.0
        elif behavior == "love":
            pulse = math.sin(phase * 6.0) * 0.8
            pose["lw"] = 10.0 + pulse
            pose["rw"] = 10.0 + pulse
            pose["lh"] = 7.5 + pulse
            pose["rh"] = 7.5 + pulse
            pose["mouth"] = 2.0
        elif behavior == "confused":
            pose["lx"] += math.sin(phase * 5.0) * 1.8
            pose["rx"] -= math.sin(phase * 3.0) * 1.5
            pose["lh"] = 7.6
            pose["rh"] = 4.8
            pose["mouth"] = 8.0
        elif behavior == "dizzy":
            pose["lh"] = 3.0
            pose["rh"] = 3.0
            pose["mouth"] = 9.0
        elif behavior == "bored":
            pose["lh"] = 2.1
            pose["rh"] = 2.1
            pose["ly"] += 2.7
            pose["ry"] += 2.7
            pose["mouth"] = 10.0
        elif behavior == "talking":
            pose["lh"] = 6.4 + math.sin(phase * 8.0) * 0.5
            pose["rh"] = pose["lh"]
            pose["mouth"] = 11.0
        elif behavior == "shy":
            pose["lh"] = 1.8
            pose["rh"] = 1.8
            pose["ly"] += 2.0
            pose["ry"] += 2.0
            pose["lx"] -= 1.0
            pose["rx"] += 1.0
            pose["mouth"] = 12.0
        elif behavior == "smug":
            pose["lh"] = 4.6
            pose["rh"] = 4.6
            pose["cut_l"] = 2.0
            pose["cut_r"] = 2.0
            pose["mouth"] = 13.0
        return pose

    def draw(self, now, dt):
        self.update_target_pose(now)
        alpha = 1.0 - math.exp(-dt * 11.0)
        for key, value in self.target.items():
            self.pose[key] = lerp(self.pose.get(key, value), value, alpha)
        canvas = [[" " for _ in range(FRAME_W)] for _ in range(FRAME_H)]
        self.render_pose(canvas, now)
        self.paint(canvas)

    def render_pose(self, canvas, now):
        mouth = round(self.pose["mouth"])
        if self.behavior == "love":
            self.draw_heart_eye(canvas, int(self.pose["lx"] + 2), int(self.pose["ly"]), now)
            self.draw_heart_eye(canvas, int(self.pose["rx"] + 2), int(self.pose["ry"]), now)
        elif self.behavior == "dizzy":
            self.draw_dizzy_eye(canvas, 15, 8, now)
            self.draw_dizzy_eye(canvas, 39, 8, now + 0.2)
        else:
            self.rounded_eye(canvas, self.pose["lx"], self.pose["ly"], self.pose["lw"], self.pose["lh"], self.pose["cut_l"], 0.0)
            self.rounded_eye(canvas, self.pose["rx"], self.pose["ry"], self.pose["rw"], self.pose["rh"], 0.0, self.pose["cut_r"])
        self.render_mouth(canvas, mouth, now)
        if self.behavior == "curious":
            self.text(canvas, 28, 3, "?")
        elif self.behavior == "sleep":
            self.text(canvas, 48, 3 + int(math.sin(now * 2.0) > 0), "z")
            self.text(canvas, 51, 2, "Z")
        elif self.behavior == "shy":
            self.text(canvas, 7, 12, "░░")
            self.text(canvas, 50, 12, "░░")
        elif self.behavior == "annoyed":
            self.text(canvas, 9, 4, "╲╲")
            self.text(canvas, 47, 4, "╱╱")

        # Sensor ambient indicators (subtle, non-intrusive)
        if self.sensors.proximity_near:
            self.text(canvas, 0, 0, "◉")           # top-left dot: someone near
        if self.sensors.is_dark:
            self.text(canvas, FRAME_W - 2, 0, "☽") # top-right: dark mode
        elif self.sensors.is_very_bright:
            self.text(canvas, FRAME_W - 2, 0, "☀") # top-right: bright
        if self.sensors.is_shaking:
            self.text(canvas, FRAME_W // 2 - 1, FRAME_H - 1, "~~~")  # bottom shake

    def rounded_eye(self, canvas, x, y, w, h, cut_left=0.0, cut_right=0.0):
        x = int(round(x))
        y = int(round(y))
        w = max(4, int(round(w)))
        h = max(1, int(round(h)))
        if h <= 2:
            self.text(canvas, x + 1, y + h // 2, "━" * max(2, w - 2))
            return
        for row in range(h):
            edge = 0
            if h >= 5 and row in (0, h - 1):
                edge = 2
            elif h >= 7 and row in (1, h - 2):
                edge = 1
            left_cut = int(cut_left * max(0, h - 1 - row) / max(1, h - 1))
            right_cut = int(cut_right * max(0, h - 1 - row) / max(1, h - 1))
            for col in range(edge + left_cut, w - edge - right_cut):
                self.put(canvas, x + col, y + row)

    def draw_heart_eye(self, canvas, x, y, now):
        bump = int(math.sin(now * 6.0) > 0)
        rows = ["██  ██", "██████", " ████ ", "  ██  "]
        for idx, row in enumerate(rows):
            self.text(canvas, x, y + idx - bump, row)

    def draw_dizzy_eye(self, canvas, x, y, now):
        phase = int(now * 8) % 4
        shape = ["╲╱", "╳ ", "╱╲", " ╳"][phase]
        self.text(canvas, x, y, shape)

    def render_mouth(self, canvas, mouth, now):
        if mouth == 0:
            return
        if mouth in (1, 8):
            self.text(canvas, 29, 12, "?")
        elif mouth == 2:
            self.text(canvas, 28, 12, "▂▂")
        elif mouth == 3:
            self.text(canvas, 27 + int(math.sin(now * 16) > 0), 12, "▔▔")
        elif mouth == 4:
            self.text(canvas, 29, 13, "▁")
        elif mouth == 5:
            self.text(canvas, 28, 12, "▔")
        elif mouth == 6:
            self.text(canvas, 29, 12, "▁")
        elif mouth == 7:
            if int(now * 2) % 2 == 0:
                self.text(canvas, 29, 12, "▁")
        elif mouth == 9:
            self.text(canvas, 27, 12, "~~~")
        elif mouth == 10:
            self.text(canvas, 27, 12, "___")
        elif mouth == 11:
            options = ["▁", "▂▂", "▃▃▃", "▂▂"]
            m = options[int(now * 10) % len(options)]
            self.text(canvas, 29 - len(m) // 2, 12, m)
        elif mouth == 12:
            self.text(canvas, 29, 12, "·")
        elif mouth == 13:
            self.text(canvas, 29, 12, "▔")

    def put(self, canvas, x, y, ch="█"):
        if 0 <= x < FRAME_W and 0 <= y < FRAME_H:
            canvas[y][x] = ch

    def text(self, canvas, x, y, value):
        for i, ch in enumerate(value):
            self.put(canvas, x + i, y, ch)

    def paint(self, canvas):
        rows, cols = self.stdscr.getmaxyx()
        top = max(0, (rows - FRAME_H) // 2)
        left = max(0, (cols - FRAME_W) // 2)
        self.stdscr.erase()
        attr = curses.A_BOLD if self.color == 0 else curses.color_pair(self.color) | curses.A_BOLD
        for y, row in enumerate(canvas):
            if top + y >= rows:
                break
            line = "".join(row)[: max(0, cols - left)]
            try:
                self.stdscr.addstr(top + y, left, line, attr)
            except curses.error:
                pass
        self.stdscr.refresh()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def behavior_duration(behavior, drives):
    if behavior == "sleep":
        return random.uniform(8.0, 18.0)
    if behavior in ("sleepy", "bored", "observe"):
        return random.uniform(5.0, 9.0)
    if behavior in ("calm", "curious", "talking"):
        return random.uniform(3.5, 7.0)
    if behavior in ("giggle", "surprised", "dizzy"):
        return random.uniform(1.8, 3.2)
    if behavior in ("annoyed", "confused", "shy", "smug"):
        return random.uniform(2.8, 5.5)
    return random.uniform(3.0, 6.0)


def main(stdscr):
    try:
        EyeApp(stdscr).run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    curses.wrapper(main)
