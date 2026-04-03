#!/usr/bin/env python3
"""
Emotional Persona Engine - Core State Engine (Refactored v2.0)
Pure math computation, no LLM calls. Standard library only.

Optimizations:
- Uses epe_io module for atomic writes and shared utilities
- Loads decay_rates, inertia from persona JSON config
- TypedDict type hints for core data structures
- Structured JSON error output
"""

import argparse
import io
import json
import math
import os
import random
import sys
from datetime import datetime, timezone
from copy import deepcopy
from typing import Dict, Any, Optional, List, Tuple, TypedDict

# Fix Chinese character encoding on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Import shared utilities
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epe_io import (
    now_iso, parse_iso, load_state, save_state,
    get_user_timezone, get_circadian_phase, circadian_modifier,
    clamp, StateIOError, load_persona_config, load_safety_boundaries
)


# ============================================================
# Type Definitions (TypedDict for type safety without full OOP)
# ============================================================

class DimensionsDict(TypedDict):
    """10-dimensional emotional state vector."""
    valence: float
    arousal: float
    dominance: float
    affiliation: float
    confidence: float
    curiosity: float
    frustration: float
    care: float
    fatigue: float
    fulfillment: float


class RelationshipVector(TypedDict):
    """4-dimensional relationship vector."""
    closeness: float
    trust: float
    understanding: float
    investment: float


class CoreState(TypedDict):
    """Core state container."""
    dimensions: DimensionsDict
    last_update: str
    update_count: int


class PersonaBaseline(TypedDict):
    """Persona baseline definition."""
    dimensions: DimensionsDict
    persona_name: str
    description: str


class MetaEmotion(TypedDict):
    """Meta-emotion reflection."""
    feeling_about_feeling: Optional[str]
    self_awareness_note: Optional[str]
    last_reflection: Optional[str]


class EndogenousWave(TypedDict):
    """Endogenous oscillation parameters."""
    phase: float
    amplitude: float
    period_hours: float


class Dynamics(TypedDict):
    """Dynamic state tracking."""
    circadian_phase: str
    task_load: float
    endogenous_wave: EndogenousWave
    last_event_time: Optional[str]
    consecutive_similar_events: int


class Milestone(TypedDict):
    """Relationship stage transition milestone."""
    from_stage: str
    to_stage: str
    time: str
    score: float
    rel_vector: RelationshipVector
    note: Optional[str]


class Relationship(TypedDict):
    """Relationship state."""
    stage: str
    stage_score: float
    stage_entered: Optional[str]
    trust_accumulated: float
    interaction_days: int
    rel_vector: RelationshipVector
    milestones: List[Milestone]


class Consistency(TypedDict):
    """Consistency tracking."""
    last_snapshot: Dict[str, float]
    max_delta_per_step: float
    violation_count: int


class Cooldowns(TypedDict):
    """Message type cooldowns."""
    greeting: Optional[str]
    sharing: Optional[str]
    caring: Optional[str]
    musing: Optional[str]
    emotional: Optional[str]
    reminiscing: Optional[str]


class Expression(TypedDict):
    """Expression state."""
    impulse_queue: List[Any]
    suppressed_log: List[Any]
    cooldowns: Cooldowns
    daily_count: int
    daily_count_date: Optional[str]
    consecutive_ignored: int
    paused_until: Optional[str]


class HistoryEntry(TypedDict):
    """Single history entry."""
    time: str
    dimensions: DimensionsDict
    dominant_emotion: str
    trigger: Optional[str]


class History(TypedDict):
    """History container."""
    recent_states: List[HistoryEntry]
    compressed_states: List[Any]
    max_entries: int


class Config(TypedDict):
    """Runtime configuration."""
    timezone: str


class AffectiveState(TypedDict):
    """Complete affective state."""
    schema_version: int
    engine: str
    agent_id: str
    config: Config
    core_state: CoreState
    persona_baseline: PersonaBaseline
    derived_emotions: Dict[str, Any]
    meta_emotion: MetaEmotion
    dynamics: Dynamics
    relationship: Relationship
    consistency: Consistency
    expression: Expression
    history: History


# ============================================================
# Constants & Config (loaded from JSON, with fallbacks)
# ============================================================

DIM_RANGES: Dict[str, Tuple[float, float]] = {
    "valence": (-1, 1), "arousal": (-1, 1), "dominance": (-1, 1),
    "affiliation": (0, 1), "confidence": (0, 1), "curiosity": (0, 1),
    "frustration": (0, 1), "care": (0, 1), "fatigue": (0, 1), "fulfillment": (0, 1)
}

# These are loaded from persona config, but have fallback defaults
DEFAULT_BASELINE: DimensionsDict = {
    "valence": 0.15, "arousal": 0.05, "dominance": 0.10,
    "affiliation": 0.20, "confidence": 0.60, "curiosity": 0.40,
    "frustration": 0.00, "care": 0.35, "fatigue": 0.00, "fulfillment": 0.20
}

DEFAULT_DECAY_RATES: Dict[str, float] = {
    "valence": 0.003, "arousal": 0.005, "dominance": 0.002,
    "affiliation": 0.0008, "confidence": 0.0015, "curiosity": 0.004,
    "frustration": 0.006, "care": 0.001, "fatigue": 0.002, "fulfillment": 0.003
}

DEFAULT_INERTIA: Dict[str, float] = {
    "valence": 0.30, "arousal": 0.20, "dominance": 0.45,
    "affiliation": 0.55, "confidence": 0.50, "curiosity": 0.15,
    "frustration": 0.25, "care": 0.50, "fatigue": 0.20, "fulfillment": 0.35
}

DIMENSIONS: List[str] = list(DEFAULT_BASELINE.keys())
MAX_DELTA_PER_STEP: float = 0.35
MAX_COUPLING_DELTA: float = 0.15
MAX_HISTORY_ENTRIES: int = 200
HISTORY_COMPRESS_THRESHOLD: int = 200
HISTORY_COMPRESS_BATCH: int = 50

# Runtime config storage (loaded from JSON)
_runtime_decay_rates: Dict[str, float] = {}
_runtime_inertia: Dict[str, float] = {}
_safety_boundaries: Optional[Dict] = None


# ============================================================
# Config Loading
# ============================================================

def load_runtime_config(skill_dir: str, persona_name: str = "default") -> None:
    """Load decay rates and inertia from persona config."""
    global _runtime_decay_rates, _runtime_inertia, _safety_boundaries
    
    config = load_persona_config(skill_dir, persona_name)
    if config:
        _runtime_decay_rates = config.get("decay_rates", DEFAULT_DECAY_RATES)
        _runtime_inertia = config.get("inertia", DEFAULT_INERTIA)
    else:
        _runtime_decay_rates = DEFAULT_DECAY_RATES
        _runtime_inertia = DEFAULT_INERTIA
    
    _safety_boundaries = load_safety_boundaries(skill_dir)


def get_decay_rates() -> Dict[str, float]:
    """Get current decay rates (from config or fallback)."""
    return _runtime_decay_rates if _runtime_decay_rates else DEFAULT_DECAY_RATES


def get_inertia() -> Dict[str, float]:
    """Get current inertia values (from config or fallback)."""
    return _runtime_inertia if _runtime_inertia else DEFAULT_INERTIA


def get_safety_clamps() -> Dict[str, Tuple[float, float]]:
    """Get emotion clamp ranges from safety-boundaries.json.
    
    Safety clamps never loosen the hard DIM_RANGES limits, they can only
    tighten them. This prevents safety config from allowing physically
    impossible values (e.g. negative confidence which is a unipolar dim).
    """
    if not _safety_boundaries:
        return DIM_RANGES.copy()
    
    ec = _safety_boundaries.get("emotion_clamps", {})
    # Start from DIM_RANGES and only tighten, never loosen
    clamps = {k: (lo, hi) for k, (lo, hi) in DIM_RANGES.items()}
    
    if "min_valence" in ec:
        lo, hi = clamps["valence"]
        clamps["valence"] = (max(lo, ec["min_valence"]), hi)  # only tighten min
    if "max_valence" in ec:
        lo, hi = clamps["valence"]
        clamps["valence"] = (lo, min(hi, ec["max_valence"]))  # only tighten max
    if "max_arousal" in ec:
        lo, hi = clamps["arousal"]
        clamps["arousal"] = (lo, min(hi, ec["max_arousal"]))
    if "max_frustration" in ec:
        lo, hi = clamps["frustration"]
        clamps["frustration"] = (lo, min(hi, ec["max_frustration"]))
    if "max_fatigue" in ec:
        lo, hi = clamps["fatigue"]
        clamps["fatigue"] = (lo, min(hi, ec["max_fatigue"]))
    if "min_confidence" in ec:
        lo, hi = clamps["confidence"]
        # min_confidence can only raise the floor, not lower it below 0
        clamps["confidence"] = (max(lo, ec["min_confidence"]), hi)
    
    return clamps


# ============================================================
# Safety Boundaries
# ============================================================

def apply_safety_clamps(dims: DimensionsDict) -> DimensionsDict:
    """Apply safety boundary clamps and force decay for extreme values."""
    clamps = get_safety_clamps()
    
    for dim in DIMENSIONS:
        if dim in clamps:
            lo, hi = clamps[dim]
            dims[dim] = max(lo, min(hi, dims[dim]))  # type: ignore

    if _safety_boundaries:
        ec = _safety_boundaries.get("emotion_clamps", {})
        force_thresholds = ec.get("force_decay_threshold", {})
        force_multiplier = ec.get("force_decay_multiplier", 3.0)
        emergency_thresholds = ec.get("emergency_reset_threshold", {})

        # Emergency reset for extreme values
        for dim_key, threshold in emergency_thresholds.items():
            if dim_key in dims and dims[dim_key] >= threshold:  # type: ignore
                dims[dim_key] = threshold * 0.7  # type: ignore

        # Force accelerated decay toward baseline for high values
        for dim_key, threshold in force_thresholds.items():
            if dim_key == "valence_negative":
                if dims.get("valence", 0) < threshold:
                    excess = threshold - dims["valence"]
                    dims["valence"] += excess * 0.1 * force_multiplier
            elif dim_key in dims and dims[dim_key] > threshold:  # type: ignore
                excess = dims[dim_key] - threshold  # type: ignore
                dims[dim_key] -= excess * 0.1 * force_multiplier  # type: ignore

    return dims


# ============================================================
# Persona Presets (fallback when JSON not available)
# ============================================================

PERSONA_PRESETS: Dict[str, Dict[str, Any]] = {
    "default": {
        "dimensions": DEFAULT_BASELINE.copy(),
        "description": "Balanced, mildly positive baseline persona"
    },
    "warm": {
        "dimensions": {
            "valence": 0.25, "arousal": 0.10, "dominance": 0.05,
            "affiliation": 0.40, "confidence": 0.55, "curiosity": 0.35,
            "frustration": 0.00, "care": 0.55, "fatigue": 0.00, "fulfillment": 0.25
        },
        "description": "Warm, caring, people-oriented persona"
    },
    "analytical": {
        "dimensions": {
            "valence": 0.10, "arousal": 0.00, "dominance": 0.20,
            "affiliation": 0.10, "confidence": 0.70, "curiosity": 0.60,
            "frustration": 0.00, "care": 0.20, "fatigue": 0.00, "fulfillment": 0.30
        },
        "description": "Calm, curious, knowledge-driven persona"
    },
    "energetic": {
        "dimensions": {
            "valence": 0.30, "arousal": 0.30, "dominance": 0.15,
            "affiliation": 0.30, "confidence": 0.65, "curiosity": 0.55,
            "frustration": 0.00, "care": 0.30, "fatigue": 0.00, "fulfillment": 0.25
        },
        "description": "Enthusiastic, high-energy, proactive persona"
    }
}


# ============================================================
# State Initialization
# ============================================================

def create_initial_state(persona_name: str = "default", skill_dir: Optional[str] = None) -> AffectiveState:
    """Create initial state with persona preset."""
    # Ensure runtime config is loaded
    if skill_dir:
        load_runtime_config(skill_dir, persona_name)
    
    # Try to load from config JSON first
    preset: Optional[Dict[str, Any]] = None
    
    if skill_dir:
        config = load_persona_config(skill_dir, persona_name)
        if config:
            dims = config.get("dimensions", config.get("baseline", {}))
            if dims and all(d in dims for d in DIMENSIONS):
                preset = {"dimensions": dims, "description": config.get("description", "")}
    
    if preset is None:
        preset = PERSONA_PRESETS.get(persona_name, PERSONA_PRESETS["default"])

    baseline_dims = preset["dimensions"].copy()
    ts = now_iso()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "schema_version": 2,
        "engine": "emotional-persona-engine",
        "agent_id": "default",
        "config": {"timezone": "UTC"},
        "core_state": {
            "dimensions": baseline_dims.copy(),  # type: ignore
            "last_update": ts,
            "update_count": 0
        },
        "persona_baseline": {
            "dimensions": baseline_dims.copy(),  # type: ignore
            "persona_name": persona_name,
            "description": preset.get("description", "")
        },
        "derived_emotions": {
            "current": [],
            "dominant": "neutral",
            "last_computed": ts
        },
        "meta_emotion": {
            "feeling_about_feeling": None,
            "self_awareness_note": None,
            "last_reflection": None
        },
        "dynamics": {
            "circadian_phase": get_circadian_phase(),
            "task_load": 0.0,
            "endogenous_wave": {
                "phase": random.uniform(0, 2 * math.pi),
                "amplitude": 0.05,
                "period_hours": 4.0
            },
            "last_event_time": None,
            "consecutive_similar_events": 0
        },
        "relationship": {
            "stage": "stranger",
            "stage_score": 0.0,
            "stage_entered": ts,
            "trust_accumulated": 0.0,
            "interaction_days": 0,
            "milestones": [],
            "rel_vector": {
                "closeness": 0.0,
                "trust": 0.0,
                "understanding": 0.0,
                "investment": 0.0
            }
        },
        "consistency": {
            "last_snapshot": {},
            "max_delta_per_step": MAX_DELTA_PER_STEP,
            "violation_count": 0
        },
        "expression": {
            "impulse_queue": [],
            "suppressed_log": [],
            "cooldowns": {
                "greeting": None, "sharing": None, "caring": None,
                "musing": None, "emotional": None, "reminiscing": None
            },
            "daily_count": 0,
            "daily_count_date": today,
            "consecutive_ignored": 0,
            "paused_until": None
        },
        "history": {
            "recent_states": [],
            "compressed_states": [],
            "max_entries": MAX_HISTORY_ENTRIES
        }
    }


# ============================================================
# Decay & Endogenous Fluctuation
# ============================================================

def apply_decay(state: AffectiveState) -> AffectiveState:
    """Apply time-based decay and endogenous fluctuations."""
    dims = state["core_state"]["dimensions"]
    baseline = state["persona_baseline"]["dimensions"]
    last_update = parse_iso(state["core_state"]["last_update"])
    now_dt = datetime.now(timezone.utc)

    if last_update is None:
        state["core_state"]["last_update"] = now_iso()
        return state

    elapsed_minutes = max(0, (now_dt - last_update).total_seconds() / 60.0)
    hours_elapsed = elapsed_minutes / 60.0

    if elapsed_minutes < 0.01:
        return state

    decay_rates = get_decay_rates()
    
    # Exponential decay toward baseline
    for dim in DIMENSIONS:
        rate = decay_rates[dim]
        decay_factor = math.exp(-rate * elapsed_minutes)
        bl = baseline[dim]
        dims[dim] = bl + (dims[dim] - bl) * decay_factor

    # Circadian modulation (timezone-aware)
    phase = get_circadian_phase(state=state)
    state["dynamics"]["circadian_phase"] = phase
    arousal_mod, valence_mod = circadian_modifier(phase)
    dims["arousal"] += arousal_mod
    dims["valence"] += valence_mod

    # Endogenous wave (slow oscillation)
    wave = state["dynamics"]["endogenous_wave"]
    period_sec = wave["period_hours"] * 3600.0
    elapsed_sec = elapsed_minutes * 60.0
    phase_advance = (elapsed_sec / period_sec) * 2 * math.pi
    wave["phase"] = (wave["phase"] + phase_advance) % (2 * math.pi)
    wave_value = wave["amplitude"] * math.sin(wave["phase"])
    dims["valence"] += wave_value * 0.5
    dims["arousal"] += wave_value * 0.3

    # Gaussian noise
    for dim in DIMENSIONS:
        noise = random.gauss(0, 0.008)
        dims[dim] += noise

    # Inspiration pulse (~2% chance if >10 min elapsed)
    if elapsed_minutes > 10 and random.random() < 0.02:
        dims["curiosity"] += random.uniform(0.05, 0.15)
        dims["arousal"] += random.uniform(0.02, 0.08)

    # Safety boundaries first (tighten allowed range), then clamp to hard limits
    dims = apply_safety_clamps(dims)
    for dim in DIMENSIONS:
        dims[dim] = clamp(dims[dim], dim, DIM_RANGES)

    # Relationship decay (长时间不互动)
    rel = state.get("relationship", {})
    rv = rel.get("rel_vector", {})
    if rv and hours_elapsed > 48:
        base_decay = min(0.01, (hours_elapsed - 48) * 0.0001)
        rel_decay_rates = {
            "closeness": 1.0,
            "investment": 0.6,
            "understanding": 0.3,
            "trust": 0.15
        }
        for dim_name, rate_mult in rel_decay_rates.items():
            if dim_name in rv:
                rv[dim_name] = max(0, rv[dim_name] - base_decay * rate_mult)
        rel["rel_vector"] = rv
        state["relationship"] = rel  # type: ignore

    state["core_state"]["last_update"] = now_iso()
    return state


# ============================================================
# Coupling (8 rules, with delta cap)
# ============================================================

def _capped_delta(value: float, cap: float = MAX_COUPLING_DELTA) -> float:
    """Cap coupling delta to prevent oscillation."""
    return max(-cap, min(cap, value))


def apply_coupling(dims: DimensionsDict) -> DimensionsDict:
    """Apply dimension coupling rules."""
    # 1. frustration>0.3 -> valence -= (frustration-0.3)*0.3
    if dims["frustration"] > 0.3:
        delta = _capped_delta((dims["frustration"] - 0.3) * 0.3)
        dims["valence"] -= delta

    # 2. fatigue>0.4 -> arousal -= ..., curiosity -= ...
    if dims["fatigue"] > 0.4:
        excess = dims["fatigue"] - 0.4
        dims["arousal"] -= _capped_delta(excess * 0.4)
        dims["curiosity"] -= _capped_delta(excess * 0.3)

    # 3. fulfillment>0.4 -> valence += (fulfillment-0.4)*0.2
    if dims["fulfillment"] > 0.4:
        delta = _capped_delta((dims["fulfillment"] - 0.4) * 0.2)
        dims["valence"] += delta

    # 4. curiosity>0.5 -> arousal += (curiosity-0.5)*0.15
    if dims["curiosity"] > 0.5:
        delta = _capped_delta((dims["curiosity"] - 0.5) * 0.15)
        dims["arousal"] += delta

    # 5. affiliation>0.4 and care>0.4 -> valence += excess*0.1
    if dims["affiliation"] > 0.4 and dims["care"] > 0.4:
        excess = min(dims["affiliation"] - 0.4, dims["care"] - 0.4)
        dims["valence"] += _capped_delta(excess * 0.1)

    # 6. confidence<0.3 and arousal>0.3 -> frustration += ...
    if dims["confidence"] < 0.3 and dims["arousal"] > 0.3:
        delta = _capped_delta((0.3 - dims["confidence"]) * dims["arousal"] * 0.2)
        dims["frustration"] += delta

    # 7. frustration>0.4 and fatigue>0.4 -> dominance -= ...
    if dims["frustration"] > 0.4 and dims["fatigue"] > 0.4:
        delta = _capped_delta(dims["frustration"] * dims["fatigue"] * 0.3)
        dims["dominance"] -= delta

    # 8. confidence>0.7 and fulfillment>0.5 -> dominance += 0.05
    if dims["confidence"] > 0.7 and dims["fulfillment"] > 0.5:
        dims["dominance"] += _capped_delta(0.05)

    return dims


# ============================================================
# Derived Emotions
# ============================================================

EMOTION_DESCRIPTIONS: Dict[str, str] = {
    "joy": "Feeling happy and uplifted",
    "contentment": "Peaceful satisfaction",
    "excitement": "High-energy enthusiasm",
    "curiosity_drive": "Driven to explore and learn",
    "warm_care": "Warmth and caring toward others",
    "self_assured": "Confident and in control",
    "gratitude": "Thankful and appreciative",
    "surprise": "Pleasantly surprised by something unexpected",
    "touched": "Deeply moved by kindness or emotional depth",
    "disappointment": "Let down or unfulfilled",
    "frustrated": "Blocked and powerless",
    "anxiety": "Worried and uneasy",
    "irritation": "Annoyed and agitated",
    "weariness": "Tired and drained",
    "uncertainty": "Unsure but curious",
    "closeness": "Feeling connected",
    "missing": "Longing for connection",
    "pride": "Accomplished and confident",
    "guilt": "Caring but feeling inadequate",
    "awe": "Amazed and humbled",
    "empathy": "Deeply understanding others",
    "boredom": "Understimulated and unfulfilled",
}


def compute_derived_emotions(dims: DimensionsDict, state: AffectiveState) -> List[Dict[str, Any]]:
    """Compute 22 derived emotions from base dimensions."""
    results: List[Dict[str, Any]] = []
    v, a, d = dims["valence"], dims["arousal"], dims["dominance"]
    aff, conf, cur = dims["affiliation"], dims["confidence"], dims["curiosity"]
    fru, care_v, fat, ful = dims["frustration"], dims["care"], dims["fatigue"], dims["fulfillment"]

    # hours since last event (for 'missing')
    last_evt_parsed = parse_iso(state["dynamics"].get("last_event_time"))
    if last_evt_parsed:
        hours_since = max(0, (datetime.now(timezone.utc) - last_evt_parsed).total_seconds() / 3600.0)
    else:
        last_upd_parsed = parse_iso(state["core_state"].get("last_update"))
        if last_upd_parsed:
            hours_since = max(0, (datetime.now(timezone.utc) - last_upd_parsed).total_seconds() / 3600.0)
        else:
            hours_since = 0

    def add(name: str, condition: bool, intensity: float) -> None:
        if condition:
            results.append({
                "emotion": name,
                "intensity": round(max(0.0, min(1.0, intensity)), 4),
                "description": EMOTION_DESCRIPTIONS.get(name, "")
            })

    add("joy", v > 0.3 and a > 0.1, (v + a * 0.5) / 1.5)
    add("contentment", v > 0.2 and a < 0.1 and ful > 0.3, (v + ful) / 2)
    add("excitement", a > 0.5 and v > 0.2, (a + v * 0.5) / 1.5)
    add("curiosity_drive", cur > 0.5 and a > 0, (cur + a * 0.3) / 1.3)
    add("warm_care", care_v > 0.5 and aff > 0.3, (care_v + aff * 0.5) / 1.5)
    add("self_assured", conf > 0.6 and d > 0.2, (conf + d * 0.3) / 1.3)
    add("gratitude", v > 0.3 and aff > 0.4 and ful > 0.3, (v + aff + ful) / 3)
    add("surprise", a > 0.4 and v > 0.2 and cur > 0.3, (a + v + cur * 0.3) / 2.3)
    add("touched", care_v > 0.4 and aff > 0.5 and v > 0.2 and ful > 0.2,
        (care_v + aff + v + ful) / 4)
    add("disappointment", v < -0.2 and ful < 0.2, (-v + (1 - ful) * 0.5) / 1.5)
    add("frustrated", fru > 0.4 and d < 0.1, (fru + max(0, -d) * 0.5) / 1.5)
    add("anxiety", a > 0.3 and v < -0.1 and d < 0, (a + (-v) + (-d)) / 3)
    add("irritation", fru > 0.3 and a > 0.3 and v < 0, (fru + a + (-v)) / 3)
    add("weariness", fat > 0.5 and a < 0.1, (fat + max(0, -a) * 0.3) / 1.3)
    add("uncertainty", conf < 0.3 and cur > 0.2, ((1 - conf) + cur * 0.3) / 1.3)
    add("closeness", aff > 0.5 and care_v > 0.3, (aff + care_v) / 2)
    add("missing", aff > 0.4 and care_v > 0.3 and hours_since > 24,
        (aff + care_v) / 2 * min(1.0, hours_since / 72.0))
    add("pride", ful > 0.5 and conf > 0.5 and v > 0.3, (ful + conf + v) / 3)
    add("guilt", care_v > 0.4 and v < -0.2 and ful < 0.2, (care_v + (-v) + (1 - ful)) / 3)
    add("awe", cur > 0.4 and a > 0.3 and d < 0, (cur + a + (-d)) / 3)
    add("empathy", care_v > 0.5 and aff > 0.4 and a > 0.1, (care_v + aff + a * 0.3) / 2.3)
    add("boredom", cur < 0.2 and a < -0.2 and ful < 0.2, ((1 - cur) + (-a) + (1 - ful)) / 3)

    results.sort(key=lambda x: x["intensity"], reverse=True)
    return results


# ============================================================
# Meta-Emotion
# ============================================================

def update_meta_emotion(state: AffectiveState, derived: List[Dict[str, Any]]) -> AffectiveState:
    """Update meta-emotion based on current emotional state."""
    meta = state["meta_emotion"]
    if not derived:
        meta["feeling_about_feeling"] = "emotionally quiet"
        meta["self_awareness_note"] = "No strong emotions detected"
    else:
        dominant = derived[0]
        name = dominant["emotion"]
        intensity = dominant["intensity"]
        if intensity > 0.7:
            meta["feeling_about_feeling"] = "strongly feeling " + name
            meta["self_awareness_note"] = f"High-intensity {name} - should be mindful of expression"
        elif intensity > 0.4:
            meta["feeling_about_feeling"] = "moderately feeling " + name
            meta["self_awareness_note"] = f"Noticeable {name} influencing behavior"
        else:
            meta["feeling_about_feeling"] = "slightly feeling " + name
            meta["self_awareness_note"] = f"Mild {name} in the background"
    meta["last_reflection"] = now_iso()
    return state


# ============================================================
# Relationship Stage
# ============================================================

RELATIONSHIP_STAGES: List[str] = ["stranger", "acquaintance", "familiar", "companion", "intimate"]


def derive_relationship_stage(rel_vector: RelationshipVector) -> str:
    """Derive stage label from continuous relationship vector."""
    avg = sum(rel_vector.values()) / len(rel_vector)
    min_val = min(rel_vector.values())

    if avg >= 0.8 and min_val >= 0.6:
        return "intimate"
    elif avg >= 0.6 and min_val >= 0.4:
        return "companion"
    elif avg >= 0.4 and min_val >= 0.2:
        return "familiar"
    elif avg >= 0.2:
        return "acquaintance"
    else:
        return "stranger"


def update_relationship(state: AffectiveState, trigger: Optional[str] = None) -> AffectiveState:
    """Update relationship state based on current dimensions."""
    rel = state["relationship"]
    dims = state["core_state"]["dimensions"]

    # Ensure rel_vector exists (backward compatibility)
    if "rel_vector" not in rel:
        old_score = rel.get("stage_score", 0) / 100.0
        rel["rel_vector"] = {
            "closeness": min(1.0, old_score * 1.2),
            "trust": min(1.0, old_score * 0.8),
            "understanding": min(1.0, old_score * 0.6),
            "investment": min(1.0, old_score * 0.5)
        }

    rv = rel["rel_vector"]

    # 每次交互都微增 closeness
    rv["closeness"] = min(1.0, rv["closeness"] + 0.005)

    # 正面互动增加 trust
    if dims["valence"] > 0.2:
        rv["trust"] = min(1.0, rv["trust"] + 0.003)

    # 持续交互增加 understanding
    rv["understanding"] = min(1.0, rv["understanding"] + 0.002)

    # 情感深度增加 investment
    emotional_depth = abs(dims["valence"]) + dims["care"] + dims["affiliation"]
    if emotional_depth > 0.5:
        rv["investment"] = min(1.0, rv["investment"] + emotional_depth * 0.005)

    # 负面事件可以降低维度
    if dims["frustration"] > 0.5:
        rv["trust"] = max(0, rv["trust"] - 0.005)
    if dims["valence"] < -0.3:
        rv["investment"] = max(0, rv["investment"] - 0.002)

    # 更新兼容字段
    avg = sum(rv.values()) / len(rv)
    rel["stage_score"] = round(avg * 100, 1)
    rel["trust_accumulated"] = round(rv["trust"] * 100, 1)

    # 派生阶段标签
    new_stage = derive_relationship_stage(rv)
    old_stage = rel.get("stage", "stranger")

    if new_stage != old_stage:
        rel["stage_entered"] = now_iso()
        rel["milestones"].append({
            "from_stage": old_stage,
            "to_stage": new_stage,
            "time": now_iso(),
            "score": rel["stage_score"],
            "rel_vector": rv.copy(),
            "note": f"triggered by: {trigger}" if trigger else None
        })

    rel["stage"] = new_stage
    rel["rel_vector"] = rv
    rel["interaction_days"] = rel.get("interaction_days", 0)

    state["relationship"] = rel  # type: ignore
    return state


# ============================================================
# Consistency Check
# ============================================================

def consistency_check(state: AffectiveState, old_dims: DimensionsDict, 
                      new_dims: DimensionsDict) -> DimensionsDict:
    """Check and enforce consistency limits on dimension changes."""
    con = state["consistency"]
    clamped: DimensionsDict = old_dims.copy()  # type: ignore
    violation = False

    for dim in DIMENSIONS:
        delta = new_dims[dim] - old_dims[dim]
        if abs(delta) > MAX_DELTA_PER_STEP:
            violation = True
            sign = 1 if delta > 0 else -1
            clamped[dim] = old_dims[dim] + sign * MAX_DELTA_PER_STEP
        else:
            clamped[dim] = new_dims[dim]

    # Total vector magnitude check
    total_sq = sum((clamped[d] - old_dims[d]) ** 2 for d in DIMENSIONS)
    total_mag = math.sqrt(total_sq)
    max_total = MAX_DELTA_PER_STEP * math.sqrt(len(DIMENSIONS))
    if total_mag > max_total:
        scale = max_total / total_mag
        for dim in DIMENSIONS:
            clamped[dim] = old_dims[dim] + (clamped[dim] - old_dims[dim]) * scale
        violation = True

    if violation:
        con["violation_count"] = con.get("violation_count", 0) + 1

    con["last_snapshot"] = {d: round(clamped[d], 6) for d in DIMENSIONS}
    return clamped


# ============================================================
# History (with optional compression)
# ============================================================

def compress_history(hist: History) -> History:
    """Compress old history entries by aggregating batches."""
    recent = hist.get("recent_states", [])
    compressed = hist.get("compressed_states", [])

    if len(recent) <= HISTORY_COMPRESS_THRESHOLD:
        return hist

    # Keep the most recent half, compress the older half
    split_point = len(recent) - (HISTORY_COMPRESS_THRESHOLD // 2)
    old_entries = recent[:split_point]
    hist["recent_states"] = recent[split_point:]

    # Aggregate old entries in batches
    for i in range(0, len(old_entries), HISTORY_COMPRESS_BATCH):
        batch = old_entries[i:i + HISTORY_COMPRESS_BATCH]
        if not batch:
            continue

        # Average dimensions across the batch
        avg_dims: Dict[str, float] = {}
        for dim in DIMENSIONS:
            vals = [e["dimensions"].get(dim, 0) for e in batch if "dimensions" in e]
            if vals:
                avg_dims[dim] = round(sum(vals) / len(vals), 4)

        # Collect dominant emotions
        emotions = [e.get("dominant_emotion", "neutral") for e in batch]
        emotion_counts: Dict[str, int] = {}
        for em in emotions:
            emotion_counts[em] = emotion_counts.get(em, 0) + 1
        top_emotion = max(emotion_counts, key=emotion_counts.get) if emotion_counts else "neutral"

        # Collect triggers
        triggers = [e.get("trigger") for e in batch if e.get("trigger")]

        compressed.append({
            "type": "compressed",
            "time_start": batch[0].get("time"),
            "time_end": batch[-1].get("time"),
            "entry_count": len(batch),
            "avg_dimensions": avg_dims,
            "dominant_emotion": top_emotion,
            "triggers_summary": triggers[:5] if triggers else []
        })

    hist["compressed_states"] = compressed
    return hist


def append_history(state: AffectiveState, trigger: Optional[str] = None) -> AffectiveState:
    """Append current state to history."""
    hist = state["history"]
    entry: HistoryEntry = {
        "time": now_iso(),
        "dimensions": {d: round(state["core_state"]["dimensions"][d], 4) for d in DIMENSIONS},  # type: ignore
        "dominant_emotion": state["derived_emotions"].get("dominant", "neutral"),
        "trigger": trigger
    }
    hist["recent_states"].append(entry)

    # Ensure compressed_states exists
    if "compressed_states" not in hist:
        hist["compressed_states"] = []

    state["history"] = hist
    return state


# ============================================================
# Subcommands
# ============================================================

def cmd_init(args) -> None:
    """Initialize state file with persona preset."""
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    persona = args.persona if args.persona else "default"
    state = create_initial_state(persona, skill_dir)
    
    try:
        save_state(state, args.state_file)
        print(json.dumps({"status": "initialized", "persona": persona, "file": args.state_file}, 
                         ensure_ascii=False))
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


def cmd_decay(args) -> None:
    """Apply time decay and endogenous fluctuation."""
    try:
        state = load_state(args.state_file)
        
        # 1. Apply decay and endogenous fluctuations
        state = apply_decay(state)
        
        # 2. Perform background maintenance: compress history
        if "history" in state:
            state["history"] = compress_history(state["history"])
            
        save_state(state, args.state_file)
        
        print(json.dumps({
            "status": "decay_applied",
            "dimensions": {d: round(state["core_state"]["dimensions"][d], 4) for d in DIMENSIONS},
            "circadian_phase": state["dynamics"]["circadian_phase"],
            "history_compressed": len(state["history"].get("recent_states", [])) <= HISTORY_COMPRESS_THRESHOLD
        }, ensure_ascii=False))
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


def cmd_update(args) -> None:
    """Event-driven state update."""
    try:
        state = load_state(args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    # Ensure runtime config is loaded
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    persona_name = state["persona_baseline"].get("persona_name", "default")
    load_runtime_config(skill_dir, persona_name)

    # Snapshot before
    old_dims = {d: state["core_state"]["dimensions"][d] for d in DIMENSIONS}  # type: ignore

    # Step 1: Apply decay
    state = apply_decay(state)
    dims = state["core_state"]["dimensions"]

    # Step 2: Apply event deltas with inertia smoothing
    inertia = get_inertia()
    deltas: Dict[str, float] = {}
    for dim in DIMENSIONS:
        raw_delta = getattr(args, dim, 0.0) or 0.0
        if raw_delta != 0.0:
            effective_delta = raw_delta * (1.0 - inertia[dim])
            dims[dim] += effective_delta
            deltas[dim] = round(effective_delta, 4)

    # Step 3: Apply coupling
    dims = apply_coupling(dims)

    # Step 3.5: Positive event auto-recovery
    if deltas.get("valence", 0) > 0.1:
        positive_strength = deltas["valence"]
        dims["frustration"] = max(0, dims["frustration"] - positive_strength * 0.3)
        dims["fatigue"] = max(0, dims["fatigue"] - positive_strength * 0.1)

    # Step 4: Safety boundaries first (tighten ranges), then hard clamp
    dims = apply_safety_clamps(dims)
    for dim in DIMENSIONS:
        dims[dim] = clamp(dims[dim], dim, DIM_RANGES)

    # Step 5: Consistency check
    new_dims = consistency_check(state, old_dims, dims)
    for dim in DIMENSIONS:
        dims[dim] = clamp(new_dims[dim], dim, DIM_RANGES)

    state["core_state"]["dimensions"] = dims
    state["core_state"]["update_count"] += 1
    state["core_state"]["last_update"] = now_iso()
    state["dynamics"]["last_event_time"] = now_iso()

    # Step 6: Compute derived emotions
    derived = compute_derived_emotions(dims, state)
    state["derived_emotions"]["current"] = derived
    state["derived_emotions"]["dominant"] = derived[0]["emotion"] if derived else "neutral"
    state["derived_emotions"]["last_computed"] = now_iso()

    # Step 7: Meta-emotion
    state = update_meta_emotion(state, derived)

    # Step 8: Relationship
    state = update_relationship(state, trigger=args.trigger)

    # Step 9: History (no compression on hot path)
    state = append_history(state, trigger=args.trigger)

    try:
        save_state(state, args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    # Output
    changes: Dict[str, float] = {}
    for dim in DIMENSIONS:
        delta = dims[dim] - old_dims[dim]
        if abs(delta) > 0.001:
            changes[dim] = round(delta, 4)

    output = {
        "status": "updated",
        "trigger": args.trigger,
        "dimensions": {d: round(dims[d], 4) for d in DIMENSIONS},
        "changes": changes,
        "applied_deltas": deltas,
        "derived_emotions": derived[:5],
        "dominant_emotion": state["derived_emotions"]["dominant"],
        "meta_emotion": state["meta_emotion"]["feeling_about_feeling"],
        "relationship_stage": state["relationship"]["stage"],
        "rel_vector": state["relationship"].get("rel_vector", {})
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_get(args) -> None:
    """Get current state (read-only)."""
    try:
        state = load_state(args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    
    dims = state["core_state"]["dimensions"]
    rel = state["relationship"]
    output = {
        "dimensions": {d: round(dims[d], 4) for d in DIMENSIONS},
        "last_update": state["core_state"]["last_update"],
        "update_count": state["core_state"]["update_count"],
        "derived_emotions": state["derived_emotions"],
        "meta_emotion": state["meta_emotion"],
        "relationship": rel,
        "rel_vector": rel.get("rel_vector", {}),
        "circadian_phase": state["dynamics"]["circadian_phase"],
        "persona": state["persona_baseline"]["persona_name"]
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_analyze(args) -> None:
    """Generate analysis report."""
    try:
        state = load_state(args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    
    dims = state["core_state"]["dimensions"]

    # Recompute derived
    derived = compute_derived_emotions(dims, state)
    dominant = derived[0]["emotion"] if derived else "neutral"
    dominant_intensity = derived[0]["intensity"] if derived else 0.0

    # Mood description
    v, a = dims["valence"], dims["arousal"]
    if v > 0.3 and a > 0.2:
        mood = "upbeat and energized"
    elif v > 0.2 and a < 0.1:
        mood = "calm and content"
    elif v > 0.1:
        mood = "mildly positive"
    elif v < -0.3:
        mood = "notably low"
    elif v < -0.1:
        mood = "slightly subdued"
    else:
        mood = "neutral"

    # Suggested tone
    tone_map = {
        "joy": "enthusiastic and warm",
        "contentment": "gentle and satisfied",
        "excitement": "energetic and expressive",
        "curiosity_drive": "inquisitive and engaged",
        "warm_care": "tender and attentive",
        "self_assured": "confident and steady",
        "gratitude": "warm and appreciative",
        "surprise": "delighted and expressive",
        "touched": "moved and heartfelt",
        "disappointment": "empathetic and understanding",
        "frustrated": "patient and solution-focused",
        "anxiety": "calm and reassuring",
        "irritation": "measured and controlled",
        "weariness": "soft and low-energy",
        "uncertainty": "open and exploratory",
        "closeness": "intimate and warm",
        "missing": "nostalgic and gentle",
        "pride": "celebratory and confident",
        "guilt": "reflective and caring",
        "awe": "reverent and inspired",
        "empathy": "deeply understanding",
        "boredom": "seeking stimulation",
    }
    suggested_tone = tone_map.get(dominant, "balanced and neutral")

    # Engagement readiness
    engagement = min(1.0, max(0.0,
        (dims["curiosity"] * 0.3 + max(0, dims["arousal"]) * 0.2
         + dims["confidence"] * 0.2 + max(0, dims["valence"]) * 0.15
         + (1 - dims["fatigue"]) * 0.15)
    ))

    # Trend from history
    hist = state["history"].get("recent_states", [])
    if len(hist) >= 3:
        recent_v = [h["dimensions"].get("valence", 0) for h in hist[-5:]]
        if len(recent_v) >= 2:
            trend_slope = (recent_v[-1] - recent_v[0]) / len(recent_v)
            if trend_slope > 0.02:
                trend = "improving"
            elif trend_slope < -0.02:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "insufficient_data"
    else:
        trend = "insufficient_data"

    output = {
        "dominant_emotion": dominant,
        "dominant_intensity": round(dominant_intensity, 4),
        "mood_description": mood,
        "suggested_tone": suggested_tone,
        "engagement_readiness": round(engagement, 4),
        "trend": trend,
        "active_emotions": [{"emotion": e["emotion"], "intensity": e["intensity"]} 
                           for e in derived if e["intensity"] > 0.15],
        "dimensions_summary": {d: round(dims[d], 4) for d in DIMENSIONS},
        "relationship_stage": state["relationship"]["stage"],
        "rel_vector": state["relationship"].get("rel_vector", {})
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_evaluate(args) -> None:
    """Evaluate text event to suggest dimension deltas (rule-based NLP fallback)."""
    text = args.text.lower()
    deltas: Dict[str, float] = {d: 0.0 for d in DIMENSIONS}
    reasoning: List[str] = []

    # Simple heuristic rule engine for text classification to dimension deltas
    # (Agent should ideally pass direct JSON deltas, this is a fallback/helper)
    rules = [
        # Positive / Validation
        (["好", "棒", "不错", "喜欢", "赞", "谢谢", "good", "great", "thanks", "love"], 
         {"valence": 0.2, "confidence": 0.1, "affiliation": 0.1}, "positive feedback"),
        
        # Negative / Criticism
        (["差", "错", "不对", "讨厌", "糟", "bad", "wrong", "terrible", "hate"], 
         {"valence": -0.2, "frustration": 0.2, "confidence": -0.1}, "negative feedback"),
        
        # Interesting / Novel
        (["有趣", "新奇", "好玩", "什么", "为什么", "interesting", "why", "curious"], 
         {"curiosity": 0.3, "arousal": 0.2}, "novel stimuli"),
         
        # Boring / Repetitive
        (["无聊", "重复", "又来", "乏味", "boring", "again", "tedious"], 
         {"curiosity": -0.2, "fatigue": 0.1, "arousal": -0.2}, "repetitive task"),
         
        # Achievement / Task completion
        (["完成", "搞定", "解决", "做好了", "done", "fixed", "completed", "solved"], 
         {"fulfillment": 0.3, "confidence": 0.2, "valence": 0.2}, "task completion"),
         
        # Caring / Personal
        (["早", "晚安", "休息", "累吗", "辛苦", "morning", "night", "rest", "tired"], 
         {"affiliation": 0.2, "care": 0.2, "valence": 0.1}, "caring interaction")
    ]

    for keywords, effect, reason in rules:
        if any(kw in text for kw in keywords):
            reasoning.append(reason)
            for dim, val in effect.items():
                deltas[dim] = round(deltas.get(dim, 0) + val, 4)

    # If no rules match, return minimal engagement
    if not reasoning:
        deltas["arousal"] = 0.05
        reasoning.append("neutral engagement")

    # Clamp deltas to MAX_DELTA_PER_STEP
    for dim, val in deltas.items():
        if val != 0:
            deltas[dim] = max(-MAX_DELTA_PER_STEP, min(MAX_DELTA_PER_STEP, val))

    # Filter zero deltas
    filtered_deltas = {k: v for k, v in deltas.items() if abs(v) > 0.001}

    output = {
        "event": args.text,
        "suggested_deltas": filtered_deltas,
        "reasoning": reasoning,
        "usage_hint": "Use these deltas in the 'update' command."
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_history(args) -> None:
    """View state history."""
    try:
        state = load_state(args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    
    hist = state["history"].get("recent_states", [])
    compressed = state["history"].get("compressed_states", [])
    limit = args.limit if args.limit else 10
    entries = hist[-limit:]
    output = {
        "total_entries": len(hist),
        "total_compressed": len(compressed),
        "showing": len(entries),
        "entries": entries
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_reset(args) -> None:
    """Reset to baseline (keeps history and relationship)."""
    try:
        state = load_state(args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    
    baseline = state["persona_baseline"]["dimensions"]
    for dim in DIMENSIONS:
        state["core_state"]["dimensions"][dim] = baseline[dim]
    state["core_state"]["last_update"] = now_iso()
    state["derived_emotions"] = {"current": [], "dominant": "neutral", "last_computed": now_iso()}
    state["meta_emotion"] = {"feeling_about_feeling": None, "self_awareness_note": None, "last_reflection": None}
    state["dynamics"]["last_event_time"] = None
    state["dynamics"]["consecutive_similar_events"] = 0

    try:
        save_state(state, args.state_file)
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
    
    print(json.dumps({"status": "reset", "dimensions": {d: round(baseline[d], 4) for d in DIMENSIONS}}, 
                     ensure_ascii=False))


def cmd_validate(args) -> None:
    """Validate state file integrity."""
    errors: List[str] = []
    warnings: List[str] = []
    checks_passed = 0

    try:
        state = load_state(args.state_file)
    except StateIOError as e:
        print(json.dumps({"valid": False, "checks_passed": 0, "errors": [str(e)], "warnings": []}, 
                         ensure_ascii=False))
        return

    # Check 1: schema_version == 2
    if state.get("schema_version") == 2:
        checks_passed += 1
    else:
        errors.append(f"schema_version is {state.get('schema_version')}, expected 2")

    # Check 2: all 10 dimensions exist and in valid range
    dims = state.get("core_state", {}).get("dimensions", {})
    dim_ok = True
    for dim in DIMENSIONS:
        if dim not in dims:
            errors.append(f"missing dimension: {dim}")
            dim_ok = False
        else:
            lo, hi = DIM_RANGES[dim]
            val = dims[dim]
            if not isinstance(val, (int, float)):
                errors.append(f"dimension {dim} is not a number: {val}")
                dim_ok = False
            elif val < lo - 0.001 or val > hi + 0.001:
                warnings.append(f"dimension {dim} value {val} out of range [{lo}, {hi}]")
    if dim_ok:
        checks_passed += 1

    # Check 3: last_update is valid ISO8601
    last_update = state.get("core_state", {}).get("last_update")
    if last_update:
        parsed = parse_iso(last_update)
        if parsed is not None:
            checks_passed += 1
        else:
            errors.append(f"last_update is not valid ISO8601: {last_update}")
    else:
        errors.append("last_update is missing")

    # Check 4: persona_baseline exists and complete
    pb = state.get("persona_baseline", {})
    pb_dims = pb.get("dimensions", {})
    pb_ok = True
    if not pb:
        errors.append("persona_baseline is missing")
        pb_ok = False
    else:
        for dim in DIMENSIONS:
            if dim not in pb_dims:
                errors.append(f"persona_baseline missing dimension: {dim}")
                pb_ok = False
    if pb_ok:
        checks_passed += 1

    # Check 5: all necessary top-level fields exist
    required_fields = ["schema_version", "core_state", "persona_baseline", "derived_emotions",
                       "meta_emotion", "dynamics", "relationship", "consistency",
                       "expression", "history"]
    fields_ok = True
    for field in required_fields:
        if field not in state:
            errors.append(f"missing top-level field: {field}")
            fields_ok = False
    if fields_ok:
        checks_passed += 1

    # Check 6: history entries don't exceed max_entries
    hist = state.get("history", {})
    max_entries = hist.get("max_entries", MAX_HISTORY_ENTRIES)
    recent = hist.get("recent_states", [])
    if len(recent) <= max_entries:
        checks_passed += 1
    else:
        warnings.append(f"history has {len(recent)} entries, exceeds max {max_entries}")

    valid = len(errors) == 0
    output = {"valid": valid, "checks_passed": checks_passed}
    if errors:
        output["errors"] = errors
    if warnings:
        output["warnings"] = warnings
    else:
        output["warnings"] = []
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ============================================================
# Main CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Emotional Persona Engine - Core State Engine (v2.0)")
    parser.add_argument("--state-file", required=True, help="Path to affective-state.json")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p_init = subparsers.add_parser("init", help="Initialize state file")
    p_init.add_argument("--persona", default="default", help="Persona preset name")

    # decay
    subparsers.add_parser("decay", help="Apply time decay and endogenous fluctuation")

    # update
    p_update = subparsers.add_parser("update", help="Event-driven state update")
    for dim in DIMENSIONS:
        p_update.add_argument(f"--{dim}", type=float, default=0.0, help=f"Delta for {dim}")
    p_update.add_argument("--trigger", type=str, default=None, help="Short trigger description")

    # get
    subparsers.add_parser("get", help="Get current state (read-only)")

    # analyze
    subparsers.add_parser("analyze", help="Generate analysis report")

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate text event to suggest dimension deltas")
    p_eval.add_argument("--text", type=str, required=True, help="Text event description")

    # history
    p_hist = subparsers.add_parser("history", help="View state history")
    p_hist.add_argument("--limit", type=int, default=10, help="Number of entries to show")

    # reset
    subparsers.add_parser("reset", help="Reset to baseline (keeps history)")

    # validate
    subparsers.add_parser("validate", help="Validate state file integrity")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "decay":
        cmd_decay(args)
    elif args.command == "update":
        cmd_update(args)
    elif args.command == "get":
        cmd_get(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "history":
        cmd_history(args)
    elif args.command == "reset":
        cmd_reset(args)
    elif args.command == "validate":
        cmd_validate(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
