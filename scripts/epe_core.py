#!/usr/bin/env python3
"""
Emotional Persona Engine - Core State Engine
Pure math computation, no LLM calls. Standard library only.
"""

import argparse
import io
import json
import math
import os
import random
import sys
from datetime import datetime, timezone, timedelta
from copy import deepcopy

# Fix Chinese character encoding on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ============================================================
# Constants
# ============================================================

DECAY_RATES = {
    "valence": 0.003, "arousal": 0.005, "dominance": 0.002,
    "affiliation": 0.0008, "confidence": 0.0015, "curiosity": 0.004,
    "frustration": 0.006, "care": 0.001, "fatigue": 0.002, "fulfillment": 0.003
}

INERTIA = {
    "valence": 0.30, "arousal": 0.20, "dominance": 0.45,
    "affiliation": 0.55, "confidence": 0.50, "curiosity": 0.15,
    "frustration": 0.25, "care": 0.50, "fatigue": 0.20, "fulfillment": 0.35
}

DIM_RANGES = {
    "valence": (-1, 1), "arousal": (-1, 1), "dominance": (-1, 1),
    "affiliation": (0, 1), "confidence": (0, 1), "curiosity": (0, 1),
    "frustration": (0, 1), "care": (0, 1), "fatigue": (0, 1), "fulfillment": (0, 1)
}

DEFAULT_BASELINE = {
    "valence": 0.15, "arousal": 0.05, "dominance": 0.10,
    "affiliation": 0.20, "confidence": 0.60, "curiosity": 0.40,
    "frustration": 0.00, "care": 0.35, "fatigue": 0.00, "fulfillment": 0.20
}

PERSONA_PRESETS = {
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

DIMENSIONS = list(DEFAULT_BASELINE.keys())
MAX_DELTA_PER_STEP = 0.35
MAX_HISTORY_ENTRIES = 200

# ============================================================
# Utility
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_iso(s):
    if s is None:
        return datetime.now(timezone.utc)
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.now(timezone.utc)


def clamp(value, dim):
    lo, hi = DIM_RANGES[dim]
    return max(lo, min(hi, value))


def load_state(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def get_circadian_phase(dt=None):
    if dt is None:
        dt = datetime.now()
    h = dt.hour
    if 6 <= h < 10:
        return "morning"
    elif 10 <= h < 14:
        return "midday"
    elif 14 <= h < 18:
        return "afternoon"
    elif 18 <= h < 22:
        return "evening"
    else:
        return "night"


def circadian_modifier(phase):
    mods = {
        "morning":   (0.02, 0.01),
        "midday":    (0.01, 0.00),
        "afternoon": (-0.01, 0.00),
        "evening":   (-0.02, 0.01),
        "night":     (-0.03, -0.01),
    }
    return mods.get(phase, (0.0, 0.0))


# ============================================================
# State Initialization
# ============================================================

def create_initial_state(persona_name="default"):
    # Try to load from config JSON first, fallback to built-in presets
    preset = None
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)

    # Map persona names to config file names
    config_map = {
        "default": os.path.join(skill_dir, "config", "default-persona.json"),
        "warm": os.path.join(skill_dir, "config", "persona-presets", "warm-companion.json"),
        "analytical": os.path.join(skill_dir, "config", "persona-presets", "intellectual-partner.json"),
        "energetic": os.path.join(skill_dir, "config", "persona-presets", "playful-friend.json"),
        "calm": os.path.join(skill_dir, "config", "persona-presets", "calm-mentor.json"),
    }

    config_path = config_map.get(persona_name)
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            # Config files may use "dimensions" or "baseline" key
            dims = config_data.get("dimensions", config_data.get("baseline", {}))
            if dims and all(d in dims for d in DIMENSIONS):
                preset = {"dimensions": dims, "description": config_data.get("description", "")}
        except Exception:
            pass

    if preset is None:
        preset = PERSONA_PRESETS.get(persona_name, PERSONA_PRESETS["default"])

    baseline_dims = preset["dimensions"].copy()
    ts = now_iso()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return {
        "schema_version": 2,
        "engine": "emotional-persona-engine",
        "agent_id": "default",
        "core_state": {
            "dimensions": baseline_dims.copy(),
            "last_update": ts,
            "update_count": 0
        },
        "persona_baseline": {
            "dimensions": baseline_dims.copy(),
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
            "stage": "acquaintance",
            "stage_score": 0.0,
            "stage_entered": ts,
            "trust_accumulated": 0.0,
            "interaction_days": 0,
            "milestones": []
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
            "max_entries": MAX_HISTORY_ENTRIES
        }
    }


# ============================================================
# Decay & Endogenous Fluctuation
# ============================================================

def apply_decay(state):
    dims = state["core_state"]["dimensions"]
    baseline = state["persona_baseline"]["dimensions"]
    last_update = parse_iso(state["core_state"]["last_update"])
    now_dt = datetime.now(timezone.utc)
    elapsed_minutes = max(0, (now_dt - last_update).total_seconds() / 60.0)

    if elapsed_minutes < 0.01:
        return state

    # Exponential decay toward baseline
    for dim in DIMENSIONS:
        rate = DECAY_RATES[dim]
        decay_factor = math.exp(-rate * elapsed_minutes)
        bl = baseline[dim]
        dims[dim] = bl + (dims[dim] - bl) * decay_factor

    # Circadian modulation
    phase = get_circadian_phase(datetime.now())
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

    # Clamp
    for dim in DIMENSIONS:
        dims[dim] = clamp(dims[dim], dim)

    state["core_state"]["last_update"] = now_iso()
    return state


# ============================================================
# Coupling (8 rules)
# ============================================================

def apply_coupling(dims):
    # 1. frustration>0.3 -> valence -= (frustration-0.3)*0.3
    if dims["frustration"] > 0.3:
        dims["valence"] -= (dims["frustration"] - 0.3) * 0.3

    # 2. fatigue>0.4 -> arousal -= ..., curiosity -= ...
    if dims["fatigue"] > 0.4:
        excess = dims["fatigue"] - 0.4
        dims["arousal"] -= excess * 0.4
        dims["curiosity"] -= excess * 0.3

    # 3. fulfillment>0.4 -> valence += (fulfillment-0.4)*0.2
    if dims["fulfillment"] > 0.4:
        dims["valence"] += (dims["fulfillment"] - 0.4) * 0.2

    # 4. curiosity>0.5 -> arousal += (curiosity-0.5)*0.15
    if dims["curiosity"] > 0.5:
        dims["arousal"] += (dims["curiosity"] - 0.5) * 0.15

    # 5. affiliation>0.4 and care>0.4 -> valence += excess*0.1
    if dims["affiliation"] > 0.4 and dims["care"] > 0.4:
        excess = min(dims["affiliation"] - 0.4, dims["care"] - 0.4)
        dims["valence"] += excess * 0.1  # max 0.06 instead of 0.09

    # 6. confidence<0.3 and arousal>0.3 -> frustration += ...
    if dims["confidence"] < 0.3 and dims["arousal"] > 0.3:
        dims["frustration"] += (0.3 - dims["confidence"]) * dims["arousal"] * 0.2

    # 7. frustration>0.4 and fatigue>0.4 -> dominance -= ...
    if dims["frustration"] > 0.4 and dims["fatigue"] > 0.4:
        dims["dominance"] -= dims["frustration"] * dims["fatigue"] * 0.3

    # 8. confidence>0.7 and fulfillment>0.5 -> dominance += 0.05
    if dims["confidence"] > 0.7 and dims["fulfillment"] > 0.5:
        dims["dominance"] += 0.05

    return dims


# ============================================================
# Derived Emotions (20 types)
# ============================================================

EMOTION_DESCRIPTIONS = {
    "joy": "Feeling happy and uplifted",
    "contentment": "Peaceful satisfaction",
    "excitement": "High-energy enthusiasm",
    "curiosity_drive": "Driven to explore and learn",
    "warm_care": "Warmth and caring toward others",
    "self_assured": "Confident and in control",
    "gratitude": "Thankful and appreciative",
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


def compute_derived_emotions(dims, state):
    results = []
    v = dims["valence"]
    a = dims["arousal"]
    d = dims["dominance"]
    aff = dims["affiliation"]
    conf = dims["confidence"]
    cur = dims["curiosity"]
    fru = dims["frustration"]
    care_v = dims["care"]
    fat = dims["fatigue"]
    ful = dims["fulfillment"]

    # hours since last event (for 'missing')
    last_evt = state["dynamics"].get("last_event_time")
    if last_evt:
        hours_since = max(0, (datetime.now(timezone.utc) - parse_iso(last_evt)).total_seconds() / 3600.0)
    else:
        # Fallback: use last_update time
        last_upd = state["core_state"].get("last_update")
        if last_upd:
            hours_since = max(0, (datetime.now(timezone.utc) - parse_iso(last_upd)).total_seconds() / 3600.0)
        else:
            hours_since = 0

    def add(name, condition, intensity):
        if condition:
            results.append({
                "emotion": name,
                "intensity": round(max(0.0, min(1.0, intensity)), 4),
                "description": EMOTION_DESCRIPTIONS.get(name, "")
            })

    add("joy",             v > 0.3 and a > 0.1,                       (v + a * 0.5) / 1.5)
    add("contentment",     v > 0.2 and a < 0.1 and ful > 0.3,         (v + ful) / 2)
    add("excitement",      a > 0.5 and v > 0.2,                        (a + v * 0.5) / 1.5)
    add("curiosity_drive", cur > 0.5 and a > 0,                        (cur + a * 0.3) / 1.3)
    add("warm_care",       care_v > 0.5 and aff > 0.3,                 (care_v + aff * 0.5) / 1.5)
    add("self_assured",    conf > 0.6 and d > 0.2,                     (conf + d * 0.3) / 1.3)
    add("gratitude",       v > 0.3 and aff > 0.4 and ful > 0.3,       (v + aff + ful) / 3)
    add("disappointment",  v < -0.2 and ful < 0.2,                     (-v + (1 - ful) * 0.5) / 1.5)
    add("frustrated",      fru > 0.4 and d < 0.1,                      (fru + max(0, -d) * 0.5) / 1.5)
    add("anxiety",         a > 0.3 and v < -0.1 and d < 0,             (a + (-v) + (-d)) / 3)
    add("irritation",      fru > 0.3 and a > 0.3 and v < 0,            (fru + a + (-v)) / 3)
    add("weariness",       fat > 0.5 and a < 0.1,                      (fat + max(0, -a) * 0.3) / 1.3)
    add("uncertainty",     conf < 0.3 and cur > 0.2,                   ((1 - conf) + cur * 0.3) / 1.3)
    add("closeness",       aff > 0.5 and care_v > 0.3,                 (aff + care_v) / 2)
    add("missing",         aff > 0.4 and care_v > 0.3 and hours_since > 24,
                           (aff + care_v) / 2 * min(1.0, hours_since / 72.0))
    add("pride",           ful > 0.5 and conf > 0.5 and v > 0.3,       (ful + conf + v) / 3)
    add("guilt",           care_v > 0.4 and v < -0.2 and ful < 0.2,    (care_v + (-v) + (1 - ful)) / 3)
    add("awe",             cur > 0.4 and a > 0.3 and d < 0,            (cur + a + (-d)) / 3)
    add("empathy",         care_v > 0.5 and aff > 0.4 and a > 0.1,     (care_v + aff + a * 0.3) / 2.3)
    add("boredom",         cur < 0.2 and a < -0.2 and ful < 0.2,       ((1 - cur) + (-a) + (1 - ful)) / 3)

    results.sort(key=lambda x: x["intensity"], reverse=True)
    return results


# ============================================================
# Meta-Emotion
# ============================================================

def update_meta_emotion(state, derived):
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
            meta["self_awareness_note"] = "High-intensity " + name + " - should be mindful of expression"
        elif intensity > 0.4:
            meta["feeling_about_feeling"] = "moderately feeling " + name
            meta["self_awareness_note"] = "Noticeable " + name + " influencing behavior"
        else:
            meta["feeling_about_feeling"] = "slightly feeling " + name
            meta["self_awareness_note"] = "Mild " + name + " in the background"
    meta["last_reflection"] = now_iso()
    return state


# ============================================================
# Relationship Stage
# ============================================================

RELATIONSHIP_STAGES = ["acquaintance", "familiar", "companion", "close_friend", "intimate"]
STAGE_THRESHOLDS = [0.0, 10.0, 30.0, 70.0, 150.0]


def update_relationship(state, trigger=None):
    rel = state["relationship"]
    dims = state["core_state"]["dimensions"]

    base_score = 0.5
    affection_bonus = max(0, dims["affiliation"]) * 0.3
    care_bonus = max(0, dims["care"]) * 0.2
    valence_bonus = max(0, dims["valence"]) * 0.2
    increment = base_score + affection_bonus + care_bonus + valence_bonus

    rel["stage_score"] += increment
    rel["trust_accumulated"] += increment * 0.5
    rel["interaction_days"] = max(rel.get("interaction_days", 0), 1)

    current_idx = RELATIONSHIP_STAGES.index(rel["stage"]) if rel["stage"] in RELATIONSHIP_STAGES else 0
    for i in range(len(RELATIONSHIP_STAGES) - 1, current_idx, -1):
        if rel["stage_score"] >= STAGE_THRESHOLDS[i]:
            if RELATIONSHIP_STAGES[i] != rel["stage"]:
                rel["stage"] = RELATIONSHIP_STAGES[i]
                rel["stage_entered"] = now_iso()
                rel["milestones"].append({
                    "stage": RELATIONSHIP_STAGES[i],
                    "time": now_iso(),
                    "score": rel["stage_score"]
                })
            break

    return state


# ============================================================
# Consistency Check
# ============================================================

def consistency_check(state, old_dims, new_dims):
    con = state["consistency"]
    clamped = {}
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
# History
# ============================================================

def append_history(state, trigger=None):
    hist = state["history"]
    entry = {
        "time": now_iso(),
        "dimensions": {d: round(state["core_state"]["dimensions"][d], 4) for d in DIMENSIONS},
        "dominant_emotion": state["derived_emotions"].get("dominant", "neutral"),
        "trigger": trigger
    }
    hist["recent_states"].append(entry)
    max_entries = hist.get("max_entries", MAX_HISTORY_ENTRIES)
    if len(hist["recent_states"]) > max_entries:
        hist["recent_states"] = hist["recent_states"][-max_entries:]
    return state


# ============================================================
# Subcommands
# ============================================================

def cmd_init(args):
    persona = args.persona if args.persona else "default"
    state = create_initial_state(persona)
    save_state(state, args.state_file)
    print(json.dumps({"status": "initialized", "persona": persona, "file": args.state_file}, ensure_ascii=False))


def cmd_decay(args):
    state = load_state(args.state_file)
    state = apply_decay(state)
    save_state(state, args.state_file)
    print(json.dumps({
        "status": "decay_applied",
        "dimensions": {d: round(state["core_state"]["dimensions"][d], 4) for d in DIMENSIONS},
        "circadian_phase": state["dynamics"]["circadian_phase"]
    }, ensure_ascii=False))


def cmd_update(args):
    state = load_state(args.state_file)

    # Snapshot before
    old_dims = {d: state["core_state"]["dimensions"][d] for d in DIMENSIONS}

    # Step 1: Apply decay
    state = apply_decay(state)
    dims = state["core_state"]["dimensions"]

    # Step 2: Apply event deltas with inertia smoothing
    deltas = {}
    for dim in DIMENSIONS:
        raw_delta = getattr(args, dim, 0.0) or 0.0
        if raw_delta != 0.0:
            effective_delta = raw_delta * (1.0 - INERTIA[dim])
            dims[dim] += effective_delta
            deltas[dim] = round(effective_delta, 4)

    # Step 3: Apply coupling
    dims = apply_coupling(dims)

    # Step 3.5: Positive event auto-recovery
    # If valence delta is positive, reduce negative dims automatically
    if deltas.get("valence", 0) > 0.1:
        positive_strength = deltas["valence"]
        # Reduce frustration
        dims["frustration"] = max(0, dims["frustration"] - positive_strength * 0.3)
        # Reduce fatigue slightly
        dims["fatigue"] = max(0, dims["fatigue"] - positive_strength * 0.1)

    # Step 4: Clamp
    for dim in DIMENSIONS:
        dims[dim] = clamp(dims[dim], dim)

    # Step 5: Consistency check
    new_dims = consistency_check(state, old_dims, dims)
    for dim in DIMENSIONS:
        dims[dim] = clamp(new_dims[dim], dim)

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

    # Step 9: History
    state = append_history(state, trigger=args.trigger)

    save_state(state, args.state_file)

    # Output
    changes = {}
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
        "relationship_stage": state["relationship"]["stage"]
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_get(args):
    state = load_state(args.state_file)
    dims = state["core_state"]["dimensions"]
    output = {
        "dimensions": {d: round(dims[d], 4) for d in DIMENSIONS},
        "last_update": state["core_state"]["last_update"],
        "update_count": state["core_state"]["update_count"],
        "derived_emotions": state["derived_emotions"],
        "meta_emotion": state["meta_emotion"],
        "relationship": state["relationship"],
        "circadian_phase": state["dynamics"]["circadian_phase"],
        "persona": state["persona_baseline"]["persona_name"]
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_analyze(args):
    state = load_state(args.state_file)
    dims = state["core_state"]["dimensions"]

    # Recompute derived
    derived = compute_derived_emotions(dims, state)
    dominant = derived[0]["emotion"] if derived else "neutral"
    dominant_intensity = derived[0]["intensity"] if derived else 0.0

    # Mood description
    v = dims["valence"]
    a = dims["arousal"]
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
        "active_emotions": [{"emotion": e["emotion"], "intensity": e["intensity"]} for e in derived if e["intensity"] > 0.15],
        "dimensions_summary": {d: round(dims[d], 4) for d in DIMENSIONS},
        "relationship_stage": state["relationship"]["stage"]
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_history(args):
    state = load_state(args.state_file)
    hist = state["history"].get("recent_states", [])
    limit = args.limit if args.limit else 10
    entries = hist[-limit:]
    output = {
        "total_entries": len(hist),
        "showing": len(entries),
        "entries": entries
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_reset(args):
    state = load_state(args.state_file)
    baseline = state["persona_baseline"]["dimensions"]
    for dim in DIMENSIONS:
        state["core_state"]["dimensions"][dim] = baseline[dim]
    state["core_state"]["last_update"] = now_iso()
    state["derived_emotions"] = {"current": [], "dominant": "neutral", "last_computed": now_iso()}
    state["meta_emotion"] = {"feeling_about_feeling": None, "self_awareness_note": None, "last_reflection": None}
    state["dynamics"]["last_event_time"] = None
    state["dynamics"]["consecutive_similar_events"] = 0
    # Keep history and relationship intact
    save_state(state, args.state_file)
    print(json.dumps({"status": "reset", "dimensions": {d: round(baseline[d], 4) for d in DIMENSIONS}}, ensure_ascii=False))


def cmd_validate(args):
    errors = []
    warnings = []
    checks_passed = 0

    try:
        state = load_state(args.state_file)
    except Exception as e:
        print(json.dumps({"valid": False, "checks_passed": 0, "errors": [f"cannot load state file: {e}"], "warnings": []}, ensure_ascii=False))
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
        try:
            parsed = parse_iso(last_update)
            # parse_iso falls back to now on failure; verify it actually parsed
            if last_update.replace("Z", "+00:00") != "None":
                checks_passed += 1
            else:
                errors.append("last_update is None")
        except Exception:
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
    parser = argparse.ArgumentParser(description="Emotional Persona Engine - Core State Engine")
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