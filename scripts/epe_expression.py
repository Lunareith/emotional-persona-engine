#!/usr/bin/env python3
"""
Emotional Persona Engine - Proactive Expression Engine
Determines when and what type of proactive message to send.
Pure math computation, no LLM calls. Standard library only.
"""

import argparse
import json
import math
import os
import random
import sys
from datetime import datetime, timezone, timedelta

# ============================================================
# Constants
# ============================================================

MESSAGE_TYPES = ["greeting", "sharing", "caring", "musing", "emotional", "reminiscing"]

# Poisson base rates (per hour)
LAMBDA = {
    "greeting": 0.12, "sharing": 0.10, "caring": 0.08,
    "musing": 0.06, "emotional": 0.03, "reminiscing": 0.02
}

# Cooldown periods (hours)
COOLDOWNS = {
    "greeting": 12, "sharing": 8, "caring": 6,
    "musing": 12, "emotional": 24, "reminiscing": 48
}

# Relationship stage multipliers [stranger, acquaintance, familiar, companion, intimate]
STAGE_ORDER = ["acquaintance", "familiar", "companion", "close_friend", "intimate"]
STAGE_MULTIPLIERS = {
    "greeting":    [0.8, 1.0, 1.0, 1.0, 1.0],
    "sharing":     [0.5, 0.8, 1.0, 1.1, 1.2],
    "caring":      [0.5, 0.8, 1.2, 1.4, 1.5],
    "musing":      [0.2, 0.6, 1.0, 1.2, 1.3],
    "emotional":   [0.0, 0.3, 0.8, 1.2, 1.5],
    "reminiscing": [0.0, 0.2, 0.7, 1.0, 1.3],
}

MAX_DAILY = 5
QUIET_START = 23  # 23:00
QUIET_END = 8     # 08:00
QUIET_MULTIPLIER = 0.1


# ============================================================
# Utility
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def parse_iso(s):
    if s is None:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None

def load_state(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def is_quiet_hours():
    h = datetime.now().hour
    if QUIET_START > QUIET_END:
        return h >= QUIET_START or h < QUIET_END
    return QUIET_START <= h < QUIET_END

def get_stage_index(stage):
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return 1  # default to acquaintance


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

def compute_suppression(expr_state, msg_type):
    """Compute suppression factor from cooldowns, ignored count, pause."""
    now_dt = datetime.now(timezone.utc)

    # Check pause
    paused_until = parse_iso(expr_state.get("paused_until"))
    if paused_until:
        if now_dt < paused_until:
            return 0.0, f"paused until {expr_state['paused_until']}"
        else:
            # Pause expired: clear pause and reset ignored counter
            expr_state["paused_until"] = None
            expr_state["consecutive_ignored"] = 0

    # Check daily limit
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if expr_state.get("daily_count_date") == today:
        if expr_state.get("daily_count", 0) >= MAX_DAILY:
            return 0.0, f"daily limit reached ({MAX_DAILY})"
    else:
        expr_state["daily_count"] = 0
        expr_state["daily_count_date"] = today

    # Check cooldown for this type
    last_sent = parse_iso(expr_state.get("cooldowns", {}).get(msg_type))
    if last_sent:
        hours_since = (now_dt - last_sent).total_seconds() / 3600.0
        cooldown = COOLDOWNS[msg_type]
        if hours_since < cooldown:
            remaining = cooldown - hours_since
            return 0.0, f"cooldown ({remaining:.1f}h remaining)"

    # Consecutive ignored penalty
    ignored = expr_state.get("consecutive_ignored", 0)
    if ignored >= 3:
        return 0.0, f"too many ignored ({ignored})"
    elif ignored > 0:
        penalty = 1.0 - (ignored * 0.3)
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

    # Late night / early morning lowers expectancy
    if hour >= 23 or hour < 8:
        base *= 0.3

    return max(0.05, min(0.95, base))


# ============================================================
# Should Trigger
# ============================================================

def should_trigger(state, state_file=None):
    """Evaluate whether to send a proactive message. Returns decision JSON."""
    dims = state["core_state"]["dimensions"]
    expr = state["expression"]
    rel_stage = state["relationship"].get("stage", "acquaintance")
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

    quiet = is_quiet_hours()
    candidates = []
    suppressed = []

    for msg_type in MESSAGE_TYPES:
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
        if quiet:
            m_quiet = QUIET_MULTIPLIER
        else:
            m_quiet = 1.0

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

    # Current hour for response expectancy calculation
    hour = datetime.now().hour

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
                # Persist state
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
    expr = state["expression"]
    expr["consecutive_ignored"] = expr.get("consecutive_ignored", 0) + 1
    if expr["consecutive_ignored"] >= 3:
        # Pause for 24 hours
        pause_until = datetime.now(timezone.utc) + timedelta(hours=24)
        expr["paused_until"] = pause_until.isoformat()
        # Log suppression
        expr["suppressed_log"].append({
            "time": now_iso(),
            "reason": "3 consecutive ignored, pausing 24h"
        })
        if len(expr["suppressed_log"]) > 50:
            expr["suppressed_log"] = expr["suppressed_log"][-50:]
    return state


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="EPE Proactive Expression Engine")
    parser.add_argument("--state-file", required=True, help="Path to affective-state.json")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("should-trigger", help="Evaluate if a proactive message should be sent")

    p_sent = subparsers.add_parser("record-sent", help="Record a sent proactive message")
    p_sent.add_argument("--type", required=True, choices=MESSAGE_TYPES, help="Message type")

    subparsers.add_parser("record-ignored", help="Record an ignored proactive message")

    args = parser.parse_args()

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


if __name__ == "__main__":
    main()
