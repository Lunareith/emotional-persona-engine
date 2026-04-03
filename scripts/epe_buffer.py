#!/usr/bin/env python3
"""
EPE Event Buffer - asynchronous settlement queue manager

Design goals:
- Zero-token append on every dialogue turn
- Trigger settlement when pending_events count reaches threshold (default 3)
- Never grow forever: claimed batches are acked and removed after success
- Never lose data: claimed batches can be requeued on failure
- Pure local script, no external dependencies
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from epe_io import now_iso

DEFAULT_BUFFER_FILENAME = "event-buffer.json"
DEFAULT_STATE_FILE = "state/affective-state.json"
DEFAULT_THRESHOLD = 3
MAX_PENDING_EVENTS = 60
MAX_INFLIGHT_BATCHES = 10


# ============================================================
# Paths / IO
# ============================================================

def get_buffer_path(state_file: str) -> str:
    state_dir = os.path.dirname(os.path.abspath(state_file))
    return os.path.join(state_dir, DEFAULT_BUFFER_FILENAME)


def _new_buffer() -> Dict[str, Any]:
    return {
        "schema_version": 2,
        "pending_events": [],
        "inflight_batches": {},
        "counters": {
            "total_appended": 0,
            "total_claimed": 0,
            "total_settled": 0,
            "total_requeued": 0,
        },
        "last_settlement": None,
        "last_settlement_note": None,
        "last_claimed_batch_id": None,
    }


def load_buffer(buffer_path: str) -> Dict[str, Any]:
    if not os.path.exists(buffer_path):
        return _new_buffer()
    try:
        with open(buffer_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # backward compatibility with v1 shape
        if "pending_events" not in data and "buffer" in data:
            upgraded = _new_buffer()
            upgraded["pending_events"] = data.get("buffer", [])
            upgraded["last_settlement"] = data.get("last_settlement")
            upgraded["counters"]["total_appended"] = data.get("total_appended", len(upgraded["pending_events"]))
            return upgraded
        return data
    except (json.JSONDecodeError, OSError):
        corrupted = _new_buffer()
        corrupted["corrupted_at"] = now_iso()
        return corrupted


def save_buffer(buffer: Dict[str, Any], buffer_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(buffer_path)), exist_ok=True)
    tmp_path = buffer_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(buffer, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, buffer_path)


# ============================================================
# Queue operations
# ============================================================

def append_event(
    state_file: str,
    user_msg: str,
    agent_reply: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    buffer_path = get_buffer_path(state_file)
    buffer = load_buffer(buffer_path)

    event = {
        "event_id": str(uuid.uuid4()),
        "time": now_iso(),
        "user_msg": user_msg,
        "agent_reply": agent_reply,
        "metadata": metadata or {},
    }
    buffer["pending_events"].append(event)
    buffer["counters"]["total_appended"] = buffer["counters"].get("total_appended", 0) + 1

    # Hard cap to prevent unbounded growth if settlement is never wired.
    # Drop oldest *pending* events only after keeping the most recent window.
    if len(buffer["pending_events"]) > MAX_PENDING_EVENTS:
        overflow = len(buffer["pending_events"]) - MAX_PENDING_EVENTS
        buffer["pending_events"] = buffer["pending_events"][overflow:]
        buffer["dropped_pending_overflow"] = buffer.get("dropped_pending_overflow", 0) + overflow

    save_buffer(buffer, buffer_path)
    pending_count = len(buffer["pending_events"])
    return {
        "appended": True,
        "buffer_path": buffer_path,
        "pending_count": pending_count,
        "should_settle": pending_count >= DEFAULT_THRESHOLD,
    }


def should_settle_now(buffer_path: str, threshold: int = DEFAULT_THRESHOLD) -> bool:
    buffer = load_buffer(buffer_path)
    return len(buffer.get("pending_events", [])) >= threshold


def claim_batch(buffer_path: str, threshold: int = DEFAULT_THRESHOLD) -> Dict[str, Any]:
    buffer = load_buffer(buffer_path)
    pending = buffer.get("pending_events", [])

    if len(buffer.get("inflight_batches", {})) >= MAX_INFLIGHT_BATCHES:
        return {
            "claimed": False,
            "reason": f"too many inflight batches (>= {MAX_INFLIGHT_BATCHES})",
            "pending_count": len(pending),
        }

    if len(pending) < threshold:
        return {
            "claimed": False,
            "reason": f"pending_count < threshold ({len(pending)} < {threshold})",
            "pending_count": len(pending),
        }

    batch_events = pending[:threshold]
    remaining = pending[threshold:]
    batch_id = f"batch-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

    buffer["pending_events"] = remaining
    buffer.setdefault("inflight_batches", {})[batch_id] = {
        "batch_id": batch_id,
        "claimed_at": now_iso(),
        "threshold": threshold,
        "event_count": len(batch_events),
        "events": batch_events,
        "status": "claimed",
    }
    buffer["last_claimed_batch_id"] = batch_id
    buffer["counters"]["total_claimed"] = buffer["counters"].get("total_claimed", 0) + len(batch_events)

    save_buffer(buffer, buffer_path)
    return {
        "claimed": True,
        "batch_id": batch_id,
        "event_count": len(batch_events),
        "events": batch_events,
        "pending_count_after_claim": len(remaining),
        "buffer_path": buffer_path,
    }


def ack_batch(buffer_path: str, batch_id: str, settlement_note: Optional[str] = None) -> Dict[str, Any]:
    buffer = load_buffer(buffer_path)
    inflight = buffer.get("inflight_batches", {})
    batch = inflight.get(batch_id)
    if not batch:
        return {"acked": False, "reason": f"batch not found: {batch_id}"}

    event_count = batch.get("event_count", len(batch.get("events", [])))
    inflight.pop(batch_id, None)
    buffer["last_settlement"] = now_iso()
    buffer["last_settlement_note"] = settlement_note
    buffer["counters"]["total_settled"] = buffer["counters"].get("total_settled", 0) + event_count
    save_buffer(buffer, buffer_path)
    return {"acked": True, "batch_id": batch_id, "event_count": event_count}


def requeue_batch(buffer_path: str, batch_id: str, note: Optional[str] = None) -> Dict[str, Any]:
    buffer = load_buffer(buffer_path)
    inflight = buffer.get("inflight_batches", {})
    batch = inflight.get(batch_id)
    if not batch:
        return {"requeued": False, "reason": f"batch not found: {batch_id}"}

    events = batch.get("events", [])
    # prepend back to queue to preserve order
    buffer["pending_events"] = events + buffer.get("pending_events", [])
    inflight.pop(batch_id, None)
    buffer["counters"]["total_requeued"] = buffer["counters"].get("total_requeued", 0) + len(events)
    if note:
        buffer["last_requeue_note"] = note
    save_buffer(buffer, buffer_path)
    return {"requeued": True, "batch_id": batch_id, "event_count": len(events)}


def get_batch(buffer_path: str, batch_id: str) -> Dict[str, Any]:
    buffer = load_buffer(buffer_path)
    batch = buffer.get("inflight_batches", {}).get(batch_id)
    if not batch:
        return {"found": False, "reason": f"batch not found: {batch_id}"}
    return {"found": True, "batch": batch}


def dump_pending(buffer_path: str) -> Dict[str, Any]:
    buffer = load_buffer(buffer_path)
    return {
        "count": len(buffer.get("pending_events", [])),
        "events": buffer.get("pending_events", []),
    }


def get_buffer_stats(buffer_path: str) -> Dict[str, Any]:
    buffer = load_buffer(buffer_path)
    pending = buffer.get("pending_events", [])
    inflight = buffer.get("inflight_batches", {})
    total_user_chars = sum(len(e.get("user_msg", "")) for e in pending)
    total_agent_chars = sum(len(e.get("agent_reply", "")) for e in pending)
    return {
        "schema_version": buffer.get("schema_version"),
        "pending_count": len(pending),
        "inflight_count": len(inflight),
        "last_settlement": buffer.get("last_settlement"),
        "last_settlement_note": buffer.get("last_settlement_note"),
        "counters": buffer.get("counters", {}),
        "estimated_pending_tokens": (total_user_chars + total_agent_chars) // 4,
        "pending_batch_ready": len(pending) >= DEFAULT_THRESHOLD,
    }


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="EPE Event Buffer Queue Manager")
    parser.add_argument("--buffer-file", help="Explicit event-buffer.json path")
    parser.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="Affective state file path")

    subparsers = parser.add_subparsers(dest="command")

    p_append = subparsers.add_parser("append", help="Append a dialogue turn event")
    p_append.add_argument("--user-msg", required=True)
    p_append.add_argument("--agent-reply", required=True)
    p_append.add_argument("--metadata-json", help="Optional metadata JSON")

    p_should = subparsers.add_parser("should-settle", help="Check if pending_count >= threshold")
    p_should.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)

    p_claim = subparsers.add_parser("claim", help="Claim one batch from pending_events")
    p_claim.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)

    p_ack = subparsers.add_parser("ack", help="Acknowledge one claimed batch")
    p_ack.add_argument("--batch-id", required=True)
    p_ack.add_argument("--note")

    p_requeue = subparsers.add_parser("requeue", help="Put one claimed batch back into pending_events")
    p_requeue.add_argument("--batch-id", required=True)
    p_requeue.add_argument("--note")

    p_get = subparsers.add_parser("get-batch", help="Get one inflight batch")
    p_get.add_argument("--batch-id", required=True)

    subparsers.add_parser("dump", help="Dump pending events")
    subparsers.add_parser("stats", help="Show buffer stats")

    args = parser.parse_args()

    buffer_path = args.buffer_file or get_buffer_path(args.state_file)

    if args.command == "append":
        metadata = json.loads(args.metadata_json) if args.metadata_json else None
        result = append_event(args.state_file, args.user_msg, args.agent_reply, metadata)
    elif args.command == "should-settle":
        result = {"should_settle": should_settle_now(buffer_path, args.threshold), "threshold": args.threshold}
    elif args.command == "claim":
        result = claim_batch(buffer_path, args.threshold)
    elif args.command == "ack":
        result = ack_batch(buffer_path, args.batch_id, args.note)
    elif args.command == "requeue":
        result = requeue_batch(buffer_path, args.batch_id, args.note)
    elif args.command == "get-batch":
        result = get_batch(buffer_path, args.batch_id)
    elif args.command == "dump":
        result = dump_pending(buffer_path)
    elif args.command == "stats":
        result = get_buffer_stats(buffer_path)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
