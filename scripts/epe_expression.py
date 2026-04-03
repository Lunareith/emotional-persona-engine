#!/usr/bin/env python3
"""
Emotional Persona Engine - Proactive Expression Engine (Refactored v2.0)
Determines when and what type of proactive message to send.

Optimizations:
- Uses epe_io module for atomic writes and shared utilities
- Fixed should_trigger side effects (only mutates if returning True or explicitly logging)
- Reads proactive_allowed from relationship-stages.json
- Reads expression_limits from safety-boundaries.json
"""

import argparse
import json
import math
import os
import random
import sys
from datetime import datetime, timezone, timedelta
from copy import deepcopy

# Import shared utilities
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epe_io import (
    now_iso, parse_iso, load_state, save_state,
    get_user_timezone, StateIOError, load_relationship_stages, load_safety_boundaries
)

# ============================================================
# Constants & Defaults (overridden by config)
# ============================================================

MESSAGE_TYPES = ["greeting", "sharing", "caring", "musing", "emotional", "reminiscing"]

# Poisson base rates (per hour)
LAMBDA = {
    "greeting": 0.12, "sharing": 0.10, "caring": 0.08,
    "musing": 0.06, "emotional": 0.03, "reminiscing": 0.02
}

# Default Cooldown periods (hours) - overridden by safety config if available
DEFAULT_COOLDOWNS = {
    "greeting": 12, "sharing": 8, "caring": 6,
    "musing": 12, "emotional": 24, "reminiscing": 48
}

# Relationship stage multipliers
STAGE_ORDER = ["stranger", "acquaintance", "familiar", "companion", "intimate"]
STAGE_MULTIPLIERS = {
    "greeting":    [0.3, 0.8, 1.0, 1.0, 1.0],
    "sharing":     [0.1, 0.5, 0.8, 1.1, 1.2],
    "caring":      [0.1, 0.5, 0.8, 1.4, 1.5],
    "musing":      [0.0, 0.2, 0.6, 1.2, 1.3],
    "emotional":   [0.0, 0.0, 0.3, 1.2, 1.5],
    "reminiscing": [0.0, 0.0, 0.2, 1.0, 1.3],
}

# Default limits - overridden by safety config
DEFAULT_MAX_DAILY = 5
DEFAULT_QUIET_START = 23  # 23:00
DEFAULT_QUIET_END = 8     # 08:00
DEFAULT_QUIET_MULTIPLIER = 0.1
DEFAULT_PAUSE_DURATION_HOURS = 24
DEFAULT_MAX_IGNORED = 3

# Runtime config storage
_runtime_limits = {
    "max_daily": DEFAULT_MAX_DAILY,
    "quiet_start": DEFAULT_QUIET_START,
    "quiet_end": DEFAULT_QUIET_END,
    "quiet_multiplier": DEFAULT_QUIET_MULTIPLIER,
    "pause_duration": DEFAULT_PAUSE_DURATION_HOURS,
    "max_ignored": DEFAULT_MAX_IGNORED,
    "min_interval_minutes": 0,
    "cooldown_negative_minutes": 0
}

_stage_proactive_allowed = {}


# ============================================================
# Config Loading
# ============================================================

def load_runtime_config():
    """Load limits from safety config and allowed types from relationship config."""
    global _runtime_limits, _stage_proactive_allowed
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Load safety boundaries for expression limits
    safety = load_safety_boundaries(skill_dir)
    if safety and "expression_limits" in safety:
        limits = safety["expression_limits"]
        if "max_daily_proactive" in limits:
            _runtime_limits["max_daily"] = limits["max_daily_proactive"]
            
        if "quiet_hours" in limits:
            qh = limits["quiet_hours"]
            if "start" in qh:
                _runtime_limits["quiet_start"] = int(qh["start"].split(":")[0])
            if "end" in qh:
                _runtime_limits["quiet_end"] = int(qh["end"].split(":")[0])
                
        if "quiet_hours_multiplier" in limits:
            _runtime_limits["quiet_multiplier"] = limits["quiet_hours_multiplier"]
            
        if "max_consecutive_ignored_before_pause" in limits:
            _runtime_limits["max_ignored"] = limits["max_consecutive_ignored_before_pause"]
            
        if "pause_duration_hours" in limits:
            _runtime_limits["pause_duration"] = limits["pause_duration_hours"]
            
        if "min_interval_between_proactive_minutes" in limits:
            _runtime_limits["min_interval_minutes"] = limits["min_interval_between_proactive_minutes"]
            
        if "cooldown_after_negative_feedback_minutes" in limits:
            _runtime_limits["cooldown_negative_minutes"] = limits["cooldown_after_negative_feedback_minutes"]

    # 2. Load relationship stages for allowed proactive types
    rel_stages = load_relationship_stages(skill_dir)
    if rel_stages and "stages" in rel_stages:
        for stage in rel_stages["stages"]:
            stage_id = stage.get("id")
            modifiers = stage.get("behavior_modifiers", {})
            allowed = modifiers.get("proactive_allowed", [])
            if stage_id and allowed:
                # Map external types to internal types if needed, or just use as is
                # The config uses names like casual_chat, share_discovery etc.
                # We need to map them to our internal 6 types
                mapped_allowed = set()
                if "greeting" in allowed: mapped_allowed.add("greeting")
                if "share_discovery" in allowed: mapped_allowed.add("sharing")
                if "casual_chat" in allowed: mapped_allowed.add("musing")
                if "express_concern" in allowed: mapped_allowed.add("caring")
                if "share_vulnerability" in allowed: mapped_allowed.add("emotional")
                if "express_missing" in allowed: mapped_allowed.add("reminiscing")
                
                # Add default fallbacks if mapping is sparse
                if not mapped_allowed and "greeting" in allowed:
                    mapped_allowed.add("greeting")
                    
                _stage_proactive_allowed[stage_id] = list(mapped_allowed)


def get_allowed_types(stage: str) -> list:
    """Get allowed message types for a relationship stage."""
    if stage in _stage_proactive_allowed and _stage_proactive_allowed[stage]:
        return _stage_proactive_allowed[stage]
    
    # Fallback to hardcoded logic if config not loaded or empty
    idx = get_stage_index(stage)
    if idx == 0: return ["greeting"]
    if idx == 1: return ["greeting", "sharing"]
    if idx == 2: return ["greeting", "sharing", "musing", "caring"]
    return MESSAGE_TYPES


# ============================================================
# Utility
# ============================================================

def is_quiet_hours(state=None):
    """Check quiet hours using the configured timezone."""
    tz = get_user_timezone(state)
    h = datetime.now(tz).hour
    start = _runtime_limits["quiet_start"]
    end = _runtime_limits["quiet_end"]
    
    if start > end:
        return h >= start or h < end
    return start <= h < end


def get_stage_index(stage):
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return 0  # default to stranger (safe fallback)


# ============================================================
# Emotion Multiplier
# ============================================================

def compute_emotion_multiplier(msg_type, dims):
    """Compute emotion-based multiplier for a message type."""
    v = dims.get("valence", 0)
    a = dims.get("arousal", 0)
    cur = dims.get("curiosity", 0)
    care = dims.get("care", 0)
    aff = dims.get("affiliation", 0)
    fru = dims.get("frustration", 0)
    fat = dims.get("fatigue", 0)
    conf = dims.get("confidence", 0)
    ful = dims.get("fulfillment", 0)

    m = 1.0

    if msg_type == "greeting":
        if v > 0.3: m *= 1.3
        if v < -0.5: m *= 0.5
        if fat > 0.7: m *= 0.1

    elif msg_type == "sharing":
        if cur > 0.5: m *= 1.5
        if v > 0.3: m *= 1.3
        if fru > 0.4: m *= 0.4
        if fat > 0.5: m *= 0.5
        if v < -0.5: m *= 0.1

    elif msg_type == "caring":
        if care > 0.5: m *= 1.8
        if aff > 0.5: m *= 1.5
        if fat > 0.7: m *= 0.6

    elif msg_type == "musing":
        if cur > 0.5: m *= 1.6
        if conf > 0.6: m *= 1.3
        if fat > 0.5: m *= 0.5
        if fru > 0.4: m *= 0.4
        if v < -0.5: m *= 0.2

    elif msg_type == "emotional":
        if aff > 0.6: m *= 1.8
        if ful > 0.5: m *= 1.5
        if conf < 0.3: m *= 0.5

    elif msg_type == "reminiscing":
        if aff > 0.5: m *= 1.5
        if v > 0.3: m *= 1.3
        if fru > 0.3: m *= 0.5

    return m


# ============================================================
# Suppression Factor
# ============================================================

def check_pause_and_limits(expr_state):
    """Check global limits and pause state without side effects.
    Returns (can_proceed, reason, should_reset_pause_flag)
    """
    now_dt = datetime.now(timezone.utc)

    # Check pause
    paused_until = parse_iso(expr_state.get("paused_until"))
    if paused_until:
        if now_dt < paused_until:
            return False, f"paused until {expr_state['paused_until']}", False
        else:
            # Pause expired, signal to caller to reset flag
            return True, "pause expired", True

    # Check daily limit
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_count = expr_state.get("daily_count", 0)
    
    # If it's a new day, count is effectively 0
    if expr_state.get("daily_count_date") != today:
        daily_count = 0
        
    if daily_count >= _runtime_limits["max_daily"]:
        return False, f"daily limit reached ({_runtime_limits['max_daily']})", False

    # Check global minimum interval
    min_interval = _runtime_limits["min_interval_minutes"]
    if min_interval > 0:
        # Find the most recent sent time across all types
        cooldowns = expr_state.get("cooldowns", {})
        latest_sent = None
        for t, time_str in cooldowns.items():
            dt = parse_iso(time_str)
            if dt and (latest_sent is None or dt > latest_sent):
                latest_sent = dt
                
        if latest_sent:
            mins_since = (now_dt - latest_sent).total_seconds() / 60.0
            if mins_since < min_interval:
                return False, f"global interval cooldown ({min_interval - mins_since:.1f}m remaining)", False

    return True, "ok", False


def compute_suppression(expr_state, msg_type):
    """Compute suppression factor for a specific message type."""
    now_dt = datetime.now(timezone.utc)

    # Check cooldown for this specific type
    last_sent = parse_iso(expr_state.get("cooldowns", {}).get(msg_type))
    if last_sent:
        hours_since = (now_dt - last_sent).total_seconds() / 3600.0
        cooldown = DEFAULT_COOLDOWNS.get(msg_type, 12)
        if hours_since < cooldown:
            remaining = cooldown - hours_since
            return 0.0, f"type cooldown ({remaining:.1f}h remaining)"

    # Consecutive ignored penalty
    ignored = expr_state.get("consecutive_ignored", 0)
    max_ignored = _runtime_limits["max_ignored"]
    
    if ignored >= max_ignored:
        return 0.0, f"too many ignored ({ignored})"
    elif ignored > 0:
        penalty = 1.0 - (ignored * (0.9 / max_ignored))
        return max(0.1, penalty), f"ignored penalty ({ignored}x)"

    return 1.0, "ok"


# ============================================================
# Inhibition & Response Expectancy Gates
# ============================================================

def compute_inhibition(dims, expression_state, relationship_stage):
    """Compute inhibition probability [0, 1]. Higher = more likely to hold back."""
    base = 0.15  # baseline inhibition

    # High fatigue → don't want to spend effort expressing
    if dims.get("fatigue", 0) > 0.4:
        base += (dims["fatigue"] - 0.4) * 0.5

    # Low confidence → not sure if should speak
    if dims.get("confidence", 0) < 0.4:
        base += (0.4 - dims.get("confidence", 0)) * 0.4

    # Previously ignored → afraid of being ignored again
    ignored = expression_state.get("consecutive_ignored", 0)
    base += ignored * 0.15

    # Relationship stage: strangers/acquaintances inhibit more
    stage_inhibition = {
        "stranger": 0.3,
        "acquaintance": 0.15,
        "familiar": 0.05,
        "companion": 0.0,
        "intimate": -0.05  # intimacy lowers inhibition
    }
    base += stage_inhibition.get(relationship_stage, 0.1)

    # Negative valence → afraid of spreading negativity
    if dims.get("valence", 0) < -0.2:
        base += abs(dims["valence"]) * 0.2

    return max(0.0, min(0.95, base))


def compute_response_expectancy(dims, expression_state, relationship_stage, msg_type, hour):
    """Compute expected response probability [0, 1]. Lower = less willing to send."""
    # Relationship stage sets the base expectancy
    stage_expect = {
        "stranger": 0.2,
        "acquaintance": 0.4,
        "familiar": 0.6,
        "companion": 0.75,
        "intimate": 0.85
    }
    base = stage_expect.get(relationship_stage, 0.4)

    # History of being ignored lowers expectancy
    ignored = expression_state.get("consecutive_ignored", 0)
    base -= ignored * 0.15

    # Message type factor (caring is most likely to get a response)
    type_factor = {
        "greeting": 0.7,
        "sharing": 0.5,
        "caring": 0.8,
        "musing": 0.3,
        "emotional": 0.6,
        "reminiscing": 0.4
    }
    base *= type_factor.get(msg_type, 0.5)

    start = _runtime_limits["quiet_start"]
    end = _runtime_limits["quiet_end"]
    is_quiet = (hour >= start or hour < end) if start > end else (start <= hour < end)
    
    if is_quiet:
        base *= 0.3

    return max(0.05, min(0.95, base))


# ============================================================
# Should Trigger
# ============================================================

def should_trigger(state, state_file=None):
    """Evaluate whether to send a proactive message. Returns decision JSON."""
    load_runtime_config()
    
    dims = state["core_state"]["dimensions"]
    expr = state["expression"]
    rel_stage = state["relationship"].get("stage", "stranger")
    stage_idx = get_stage_index(rel_stage)

    # Time since last event
    last_evt = parse_iso(state["dynamics"].get("last_event_time"))
    now_dt = datetime.now(timezone.utc)
    if last_evt:
        hours_since_event = (now_dt - last_evt).total_seconds() / 3600.0
    else:
        hours_since_event = 24  # assume long silence if no data

    # Must have at least some silence
    if hours_since_event < 0.5:
        return {
            "should_send": False,
            "reason": "too recent interaction",
            "hours_since_event": round(hours_since_event, 2)
        }

    # Gate 0: Global limits (pause, daily count, global cooldown)
    can_proceed, limit_reason, needs_pause_reset = check_pause_and_limits(expr)
    
    state_mutated = False
    if needs_pause_reset:
        expr["paused_until"] = None
        expr["consecutive_ignored"] = 0
        state_mutated = True
        
    if not can_proceed:
        if state_mutated and state_file:
            save_state(state, state_file)
        return {
            "should_send": False,
            "reason": limit_reason,
            "hours_since_event": round(hours_since_event, 2)
        }

    quiet = is_quiet_hours(state)
    candidates = []
    suppressed = []
    
    # Filter allowed types by relationship stage
    allowed_types = get_allowed_types(rel_stage)

    for msg_type in MESSAGE_TYPES:
        if msg_type not in allowed_types:
            suppressed.append({
                "type": msg_type,
                "reason": f"not allowed in stage '{rel_stage}'",
                "base_probability": 0
            })
            continue
            
        # Base probability (Poisson)
        lam = LAMBDA[msg_type]
        p_base = 1.0 - math.exp(-lam * hours_since_event)

        # Emotion multiplier
        m_emotion = compute_emotion_multiplier(msg_type, dims)

        # Relationship multiplier
        m_relationship = STAGE_MULTIPLIERS[msg_type][stage_idx]

        # Suppression
        m_suppression, supp_reason = compute_suppression(expr, msg_type)

        # Quiet hours
        m_quiet = _runtime_limits["quiet_multiplier"] if quiet else 1.0

        # Final probability
        p_final = p_base * m_emotion * m_relationship * m_suppression * m_quiet

        if m_suppression == 0.0:
            suppressed.append({
                "type": msg_type,
                "reason": supp_reason,
                "base_probability": round(p_base, 4)
            })
        else:
            candidates.append({
                "type": msg_type,
                "probability": round(p_final, 4),
                "p_base": round(p_base, 4),
                "m_emotion": round(m_emotion, 4),
                "m_relationship": round(m_relationship, 4),
                "m_suppression": round(m_suppression, 4)
            })

    # Sort by probability desc
    candidates.sort(key=lambda x: x["probability"], reverse=True)

    # Current hour (timezone-aware) for response expectancy calculation
    tz = get_user_timezone(state)
    hour = datetime.now(tz).hour

    # Roll dice for each candidate
    for c in candidates:
        roll = random.random()
        if roll < c["probability"]:
            best_type = c["type"]
            probability = c["probability"]

            # Gate 1: Inhibition check
            inhibition = compute_inhibition(dims, expr, rel_stage)
            if random.random() < inhibition:
                # Wanted to say but held back → log to suppressed_log
                suppressed_entry = {
                    "time": now_iso(),
                    "message_type": best_type,
                    "probability": probability,
                    "inhibition": round(inhibition, 4),
                    "reason": "inhibition_triggered"
                }
                if "suppressed_log" not in expr:
                    expr["suppressed_log"] = []
                expr["suppressed_log"].append(suppressed_entry)
                # Keep only the most recent 20 entries
                if len(expr["suppressed_log"]) > 20:
                    expr["suppressed_log"] = expr["suppressed_log"][-20:]
                
                # Persist state because we logged suppression
                if state_file:
                    save_state(state, state_file)
                    
                return {
                    "should_send": False,
                    "reason": "inhibited (wanted to say but held back)",
                    "message_type": best_type,
                    "probability": probability,
                    "inhibition": round(inhibition, 4),
                    "suppressed": True,
                    "hours_since_event": round(hours_since_event, 2),
                    "quiet_hours": quiet
                }

            # Gate 2: Response expectancy check
            resp_expect = compute_response_expectancy(dims, expr, rel_stage, best_type, hour)
            if resp_expect < 0.25:
                if state_mutated and state_file:
                    save_state(state, state_file)
                return {
                    "should_send": False,
                    "reason": f"low response expectancy ({resp_expect:.2f})",
                    "message_type": best_type,
                    "probability": probability,
                    "inhibition": round(inhibition, 4),
                    "response_expectancy": round(resp_expect, 4),
                    "hours_since_event": round(hours_since_event, 2),
                    "quiet_hours": quiet
                }

            # All gates passed
            if state_mutated and state_file:
                save_state(state, state_file)
                
            return {
                "should_send": True,
                "message_type": best_type,
                "probability": probability,
                "roll": round(roll, 4),
                "inhibition": round(inhibition, 4),
                "response_expectancy": round(resp_expect, 4),
                "reason": "passed all gates",
                "hours_since_event": round(hours_since_event, 2),
                "quiet_hours": quiet,
                "suppressed_types": suppressed
            }

    if state_mutated and state_file:
        save_state(state, state_file)
        
    return {
        "should_send": False,
        "reason": "no trigger passed probability check",
        "top_candidate": candidates[0] if candidates else None,
        "hours_since_event": round(hours_since_event, 2),
        "quiet_hours": quiet,
        "suppressed_types": suppressed
    }


# ============================================================
# Record Sent / Ignored
# ============================================================

def record_sent(state, msg_type):
    """Record that a proactive message was sent."""
    load_runtime_config()
    expr = state["expression"]
    expr["cooldowns"][msg_type] = now_iso()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if expr.get("daily_count_date") != today:
        expr["daily_count"] = 0
        expr["daily_count_date"] = today
        
    expr["daily_count"] = expr.get("daily_count", 0) + 1
    expr["consecutive_ignored"] = 0  # reset on successful send
    return state


def record_ignored(state):
    """Record that a proactive message was ignored by user."""
    load_runtime_config()
    expr = state["expression"]
    expr["consecutive_ignored"] = expr.get("consecutive_ignored", 0) + 1
    
    max_ignored = _runtime_limits["max_ignored"]
    pause_hours = _runtime_limits["pause_duration"]
    
    if expr["consecutive_ignored"] >= max_ignored:
        # Pause
        pause_until = datetime.now(timezone.utc) + timedelta(hours=pause_hours)
        expr["paused_until"] = pause_until.isoformat()
        
        # Log suppression
        if "suppressed_log" not in expr:
            expr["suppressed_log"] = []
            
        expr["suppressed_log"].append({
            "time": now_iso(),
            "reason": f"{max_ignored} consecutive ignored, pausing {pause_hours}h"
        })
        if len(expr["suppressed_log"]) > 50:
            expr["suppressed_log"] = expr["suppressed_log"][-50:]
            
    return state


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="EPE Proactive Expression Engine (v2.0)")
    parser.add_argument("--state-file", required=True, help="Path to affective-state.json")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("should-trigger", help="Evaluate if a proactive message should be sent")

    p_sent = subparsers.add_parser("record-sent", help="Record a sent proactive message")
    p_sent.add_argument("--type", required=True, choices=MESSAGE_TYPES, help="Message type")

    subparsers.add_parser("record-ignored", help="Record an ignored proactive message")

    args = parser.parse_args()

    try:
        if args.command == "should-trigger":
            state = load_state(args.state_file)
            result = should_trigger(state, state_file=args.state_file)
            print(json.dumps(result, ensure_ascii=False, indent=2))

        elif args.command == "record-sent":
            state = load_state(args.state_file)
            state = record_sent(state, args.type)
            save_state(state, args.state_file)
            print(json.dumps({"status": "recorded", "type": args.type}, ensure_ascii=False))

        elif args.command == "record-ignored":
            state = load_state(args.state_file)
            state = record_ignored(state)
            save_state(state, args.state_file)
            print(json.dumps({
                "status": "recorded",
                "consecutive_ignored": state["expression"]["consecutive_ignored"],
                "paused": state["expression"].get("paused_until") is not None
            }, ensure_ascii=False))

        else:
            parser.print_help()
            sys.exit(1)
            
    except StateIOError as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
