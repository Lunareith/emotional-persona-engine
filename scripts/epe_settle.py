#!/usr/bin/env python3
"""
EPE Async Settlement Helper

This script does NOT call any external model provider directly.
Instead, it prepares a claimed batch + prompt for an external caller
(OpenClaw workflow / isolated agentTurn using Qwen-Turbo), then applies
returned deltas back into the main affective state safely.

Flow:
1. prepare  -> claim 3 pending events from event-buffer.json and print prompt
2. external Qwen-Turbo call analyzes batch and returns settlement JSON
3. apply    -> apply deltas to affective-state.json and ack claimed batch
4. abort    -> on failure, requeue claimed batch back to pending_events
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epe_io import load_state, save_state, now_iso, StateIOError
import epe_core
import epe_buffer

DEFAULT_MODEL = "qwen-turbo"
DEFAULT_THRESHOLD = 3


# ============================================================
# Prompt building
# ============================================================

def _round_dims(dims: Dict[str, float]) -> Dict[str, float]:
    return {k: round(v, 4) for k, v in dims.items()}


def build_settlement_prompt(state: Dict[str, Any], events: List[Dict[str, Any]]) -> str:
    dims = state["core_state"]["dimensions"]
    rel = state.get("relationship", {})
    derived = state.get("derived_emotions", {}).get("current", [])[:5]

    lines: List[str] = []
    lines.append("你是 EPE（Emotional Persona Engine）的异步情绪结算器。")
    lines.append("你的任务：阅读下面最近 3 条对话事件，评估这些事件对 Agent 自身内部情绪状态的净影响。")
    lines.append("注意：评估的是 Agent 自己的感受，不是用户情绪。")
    lines.append("")
    lines.append("【当前状态快照】")
    lines.append(json.dumps({
        "dimensions": _round_dims(dims),
        "dominant_emotion": state.get("derived_emotions", {}).get("dominant", "neutral"),
        "relationship_stage": rel.get("stage", "stranger"),
        "active_emotions": [{"emotion": e.get("emotion"), "intensity": e.get("intensity")} for e in derived],
    }, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("【待结算事件】")
    for idx, event in enumerate(events, start=1):
        lines.append(f"事件 {idx} @ {event.get('time')}")
        lines.append(f"用户: {event.get('user_msg', '')}")
        lines.append(f"Agent: {event.get('agent_reply', '')}")
        lines.append("")

    lines.append("【评估原则】")
    lines.append("1. 这是批量净影响，不要逐句机械相加。")
    lines.append("2. 只输出真正变化的维度，忽略微不足道的变化。")
    lines.append("3. 单个维度建议变化量尽量控制在 -0.35 ~ +0.35。")
    lines.append("4. 常见映射示例：")
    lines.append("   - 被认可/被感谢 -> valence↑ confidence↑ affiliation↑")
    lines.append("   - 被否定/被催促/被误解 -> valence↓ frustration↑ confidence↓")
    lines.append("   - 有趣的新问题 -> curiosity↑ arousal↑")
    lines.append("   - 重复、琐碎、机械任务 -> fatigue↑ curiosity↓")
    lines.append("   - 被托付重要事情 -> care↑ fulfillment↑")
    lines.append("5. 不要输出最终状态，只输出 delta。")
    lines.append("")
    lines.append("【输出要求】")
    lines.append("只输出合法 JSON，不要加 markdown 代码块，不要附加解释。")
    lines.append("格式如下：")
    lines.append(json.dumps({
        "deltas": {
            "valence": 0.12,
            "curiosity": 0.18,
            "frustration": -0.05
        },
        "reasoning": "一句话总结这批事件对 Agent 情绪的净影响",
        "confidence": 0.82
    }, ensure_ascii=False, indent=2))
    return "\n".join(lines)


# ============================================================
# Settlement application
# ============================================================

def apply_deltas_to_state(
    state: Dict[str, Any],
    deltas: Dict[str, float],
    trigger: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply settlement deltas using the same pipeline as epe_core update."""
    persona_name = state["persona_baseline"].get("persona_name", "default")
    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    epe_core.load_runtime_config(skill_dir, persona_name)

    old_dims = {d: state["core_state"]["dimensions"][d] for d in epe_core.DIMENSIONS}

    # 1. decay first
    state = epe_core.apply_decay(state)
    dims = state["core_state"]["dimensions"]

    # 2. apply settlement deltas with inertia
    inertia = epe_core.get_inertia()
    applied_deltas: Dict[str, float] = {}
    for dim in epe_core.DIMENSIONS:
        raw_delta = float(deltas.get(dim, 0.0) or 0.0)
        if raw_delta != 0.0:
            effective_delta = raw_delta * (1.0 - inertia[dim])
            dims[dim] += effective_delta
            applied_deltas[dim] = round(effective_delta, 4)

    # 3. coupling
    dims = epe_core.apply_coupling(dims)

    # 4. positive auto-recovery
    if applied_deltas.get("valence", 0) > 0.1:
        positive_strength = applied_deltas["valence"]
        dims["frustration"] = max(0, dims["frustration"] - positive_strength * 0.3)
        dims["fatigue"] = max(0, dims["fatigue"] - positive_strength * 0.1)

    # 5. safety + hard clamp
    dims = epe_core.apply_safety_clamps(dims)
    for dim in epe_core.DIMENSIONS:
        dims[dim] = epe_core.clamp(dims[dim], dim, epe_core.DIM_RANGES)

    # 6. consistency
    new_dims = epe_core.consistency_check(state, old_dims, dims)
    for dim in epe_core.DIMENSIONS:
        dims[dim] = epe_core.clamp(new_dims[dim], dim, epe_core.DIM_RANGES)

    state["core_state"]["dimensions"] = dims
    state["core_state"]["update_count"] += 1
    state["core_state"]["last_update"] = now_iso()
    state["dynamics"]["last_event_time"] = now_iso()

    # 7. derived/meta/relationship/history
    derived = epe_core.compute_derived_emotions(dims, state)
    state["derived_emotions"]["current"] = derived
    state["derived_emotions"]["dominant"] = derived[0]["emotion"] if derived else "neutral"
    state["derived_emotions"]["last_computed"] = now_iso()

    state = epe_core.update_meta_emotion(state, derived)
    state = epe_core.update_relationship(state, trigger=trigger)
    state = epe_core.append_history(state, trigger=trigger)
    return state


# ============================================================
# Commands
# ============================================================

def cmd_prepare(args) -> None:
    state = load_state(args.state_file)
    buffer_path = epe_buffer.get_buffer_path(args.state_file)
    claim = epe_buffer.claim_batch(buffer_path, threshold=args.threshold)
    if not claim.get("claimed"):
        print(json.dumps({
            "prepared": False,
            "reason": claim.get("reason"),
            "buffer_path": buffer_path,
            "threshold": args.threshold,
        }, ensure_ascii=False, indent=2))
        return

    batch_id = claim["batch_id"]
    events = claim["events"]
    prompt = build_settlement_prompt(state, events)
    print(json.dumps({
        "prepared": True,
        "batch_id": batch_id,
        "model": args.model,
        "event_count": len(events),
        "buffer_path": buffer_path,
        "prompt": prompt,
        "usage": {
            "next_step": "Send the prompt to the configured small model and then call apply with its JSON output.",
            "expected_apply": f"python scripts/epe_settle.py --state-file {args.state_file} apply --batch-id {batch_id} --settlement-json '<JSON>'"
        }
    }, ensure_ascii=False, indent=2))


def _parse_settlement_payload(settlement_json: str) -> Dict[str, Any]:
    payload = json.loads(settlement_json)
    if not isinstance(payload, dict):
        raise ValueError("settlement-json must decode to an object")
    deltas = payload.get("deltas")
    if not isinstance(deltas, dict):
        raise ValueError("settlement-json must contain object field 'deltas'")
    return payload


def cmd_apply(args) -> None:
    buffer_path = epe_buffer.get_buffer_path(args.state_file)
    batch_result = epe_buffer.get_batch(buffer_path, args.batch_id)
    if not batch_result.get("found"):
        print(json.dumps({"applied": False, "reason": batch_result.get("reason")}, ensure_ascii=False, indent=2))
        sys.exit(1)

    settlement = _parse_settlement_payload(args.settlement_json)
    deltas = settlement.get("deltas", {})
    reasoning = settlement.get("reasoning", "async settlement")
    confidence = settlement.get("confidence")

    state = load_state(args.state_file)
    trigger = f"async_settlement[{args.batch_id}]: {reasoning}"
    state = apply_deltas_to_state(state, deltas, trigger=trigger)
    save_state(state, args.state_file)

    note = f"{reasoning} | confidence={confidence}" if confidence is not None else reasoning
    ack = epe_buffer.ack_batch(buffer_path, args.batch_id, settlement_note=note)

    print(json.dumps({
        "applied": True,
        "batch_id": args.batch_id,
        "ack": ack,
        "deltas": deltas,
        "reasoning": reasoning,
        "confidence": confidence,
        "dominant_emotion": state["derived_emotions"].get("dominant", "neutral"),
        "dimensions": {k: round(v, 4) for k, v in state["core_state"]["dimensions"].items()},
    }, ensure_ascii=False, indent=2))


def cmd_abort(args) -> None:
    buffer_path = epe_buffer.get_buffer_path(args.state_file)
    result = epe_buffer.requeue_batch(buffer_path, args.batch_id, note=args.note)
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="EPE async settlement helper")
    parser.add_argument("--state-file", required=True, help="Path to affective-state.json")

    subparsers = parser.add_subparsers(dest="command")

    p_prepare = subparsers.add_parser("prepare", help="Claim one batch and build settlement prompt")
    p_prepare.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    p_prepare.add_argument("--model", default=DEFAULT_MODEL, help="Configured small model name, e.g. qwen-turbo")

    p_apply = subparsers.add_parser("apply", help="Apply settlement JSON and ack claimed batch")
    p_apply.add_argument("--batch-id", required=True)
    p_apply.add_argument("--settlement-json", required=True, help="Raw JSON string returned by the settlement model")

    p_abort = subparsers.add_parser("abort", help="Abort one claimed batch and put it back to pending")
    p_abort.add_argument("--batch-id", required=True)
    p_abort.add_argument("--note")

    args = parser.parse_args()

    try:
        if args.command == "prepare":
            cmd_prepare(args)
        elif args.command == "apply":
            cmd_apply(args)
        elif args.command == "abort":
            cmd_abort(args)
        else:
            parser.print_help()
            sys.exit(1)
    except (StateIOError, ValueError, json.JSONDecodeError) as e:
        print(json.dumps({"error": str(e), "success": False}, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
