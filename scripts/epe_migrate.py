#!/usr/bin/env python3
"""
Emotional Persona Engine - Migration Tool
Migrate from emotion-ai emotion-state.json to EPE affective-state.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

DEFAULT_BASELINE = {
    "valence": 0.15, "arousal": 0.05, "dominance": 0.10,
    "affiliation": 0.20, "confidence": 0.60, "curiosity": 0.40,
    "frustration": 0.00, "care": 0.35, "fatigue": 0.00, "fulfillment": 0.20
}

def migrate(old_path, new_path):
    with open(old_path, "r", encoding="utf-8") as f:
        old = json.load(f)

    # Extract old dimensions (from default user or first user)
    users = old.get("users", {})
    user_key = "default" if "default" in users else (list(users.keys())[0] if users else None)
    
    if user_key and users.get(user_key, {}).get("current"):
        old_dims = users[user_key]["current"]
    else:
        old_dims = {}

    # Map old 6-dim to new 10-dim
    new_dims = DEFAULT_BASELINE.copy()
    
    # Direct mappings
    if "valence" in old_dims:
        new_dims["valence"] = old_dims["valence"]
    if "arousal" in old_dims:
        new_dims["arousal"] = old_dims["arousal"]
    if "dominance" in old_dims:
        new_dims["dominance"] = old_dims["dominance"]
    
    # trust → affiliation (rename + meaning shift)
    if "trust" in old_dims:
        new_dims["affiliation"] = old_dims["trust"]
    
    # anticipation → curiosity * 0.7 + fulfillment * 0.3
    if "anticipation" in old_dims:
        ant = old_dims["anticipation"]
        new_dims["curiosity"] = max(0, min(1, ant * 0.7 + DEFAULT_BASELINE["curiosity"] * 0.3))
        new_dims["fulfillment"] = max(0, min(1, ant * 0.3 + DEFAULT_BASELINE["fulfillment"] * 0.7))
    
    # confusion → frustration * 0.6 + (1-confidence) * 0.4
    if "confusion" in old_dims:
        conf_val = old_dims["confusion"]
        new_dims["frustration"] = max(0, min(1, conf_val * 0.6))
        new_dims["confidence"] = max(0, min(1, 1.0 - conf_val * 0.4))
    
    # New dimensions keep defaults
    # care, fatigue stay at baseline

    # Build new state
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    new_state = {
        "schema_version": 2,
        "engine": "emotional-persona-engine",
        "agent_id": "default",
        "core_state": {
            "dimensions": new_dims,
            "last_update": now,
            "update_count": 0
        },
        "persona_baseline": {
            "dimensions": DEFAULT_BASELINE.copy(),
            "persona_name": "migrated",
            "description": "Migrated from emotion-ai"
        },
        "derived_emotions": {"current": [], "dominant": "neutral", "last_computed": now},
        "meta_emotion": {"feeling_about_feeling": None, "self_awareness_note": None, "last_reflection": None},
        "dynamics": {
            "circadian_phase": "morning", "task_load": 0.0,
            "endogenous_wave": {"phase": 0.0, "amplitude": 0.05, "period_hours": 4.0},
            "last_event_time": None, "consecutive_similar_events": 0
        },
        "relationship": {
            "stage": "familiar",  # assume existing relationship
            "stage_score": 50.0,
            "stage_entered": now,
            "trust_accumulated": 25.0,
            "interaction_days": old.get("users", {}).get(user_key, {}).get("metadata", {}).get("total_interactions", 0),
            "milestones": [{"stage": "familiar", "time": now, "score": 50.0, "note": "migrated from emotion-ai"}]
        },
        "consistency": {"last_snapshot": {}, "max_delta_per_step": 0.35, "violation_count": 0},
        "expression": {
            "impulse_queue": [], "suppressed_log": [],
            "cooldowns": {"greeting": None, "sharing": None, "caring": None, "musing": None, "emotional": None, "reminiscing": None},
            "daily_count": 0, "daily_count_date": today, "consecutive_ignored": 0, "paused_until": None
        },
        "history": {"recent_states": [], "max_entries": 200}
    }

    # Migrate history if available
    old_history = old.get("users", {}).get(user_key, {}).get("history", [])
    for entry in old_history[-50:]:  # take last 50
        new_state["history"]["recent_states"].append({
            "time": entry.get("timestamp", now),
            "dimensions": {
                "valence": entry.get("after", {}).get("valence", 0),
                "arousal": entry.get("after", {}).get("arousal", 0),
                "dominance": entry.get("after", {}).get("dominance", 0),
                "affiliation": entry.get("after", {}).get("trust", 0.2),
                "confidence": 0.6, "curiosity": 0.4, "frustration": 0.0,
                "care": 0.35, "fatigue": 0.0, "fulfillment": 0.2
            },
            "dominant_emotion": "neutral",
            "trigger": entry.get("trigger", "migrated")
        })

    os.makedirs(os.path.dirname(os.path.abspath(new_path)), exist_ok=True)
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, ensure_ascii=False)

    return {
        "status": "migrated",
        "old_dimensions": old_dims,
        "new_dimensions": new_dims,
        "history_entries_migrated": len(new_state["history"]["recent_states"]),
        "relationship_stage": "familiar",
        "output_file": new_path
    }


def main():
    parser = argparse.ArgumentParser(description="Migrate emotion-ai state to EPE format")
    parser.add_argument("--old", required=True, help="Path to old emotion-state.json")
    parser.add_argument("--new", required=True, help="Path for new affective-state.json")
    args = parser.parse_args()

    if not os.path.exists(args.old):
        print(json.dumps({"error": f"File not found: {args.old}"}))
        sys.exit(1)

    result = migrate(args.old, args.new)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
