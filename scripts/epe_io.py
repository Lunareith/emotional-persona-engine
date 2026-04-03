#!/usr/bin/env python3
"""
EPE IO Module - Common utilities for state persistence and time handling
Provides atomic writes, backup recovery, and timezone support.
"""

import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any


# ============================================================
# Time Utilities
# ============================================================

def now_iso() -> str:
    """Get current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(s: Optional[str]) -> Optional[datetime]:
    """Parse ISO8601 string. Returns None if s is None or unparseable."""
    if s is None:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


# ============================================================
# Timezone Utilities
# ============================================================

def get_user_timezone(state: Optional[Dict[str, Any]] = None) -> timezone:
    """Get user timezone from state config, default to UTC."""
    tz_name = None
    if state:
        tz_name = state.get("config", {}).get("timezone")
    if not tz_name:
        tz_name = "UTC"
    
    # Python 3.9+ has zoneinfo; fallback to fixed offset for common zones
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except (ImportError, KeyError):
        if tz_name == "UTC" or tz_name == "UTC+0":
            return timezone.utc
        if tz_name.startswith("UTC"):
            try:
                offset_str = tz_name[3:]
                offset_hours = int(offset_str)
                return timezone(timedelta(hours=offset_hours))
            except (ValueError, IndexError):
                pass
        return timezone.utc


def get_circadian_phase(dt: Optional[datetime] = None, 
                        state: Optional[Dict[str, Any]] = None) -> str:
    """Get current circadian phase based on user's timezone."""
    if dt is None:
        tz = get_user_timezone(state)
        dt = datetime.now(tz)
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


def circadian_modifier(phase: str) -> Tuple[float, float]:
    """Get (valence_mod, arousal_mod) for a circadian phase."""
    mods = {
        "morning":   (0.02, 0.01),
        "midday":    (0.01, 0.00),
        "afternoon": (-0.01, 0.00),
        "evening":   (-0.02, 0.01),
        "night":     (-0.03, -0.01),
    }
    return mods.get(phase, (0.0, 0.0))


# ============================================================
# State IO with Atomic Writes and Backup Recovery
# ============================================================

class StateIOError(Exception):
    """Custom exception for state IO errors."""
    pass


def load_state(path: str, allow_backup: bool = True) -> Dict[str, Any]:
    """
    Load state from JSON file.
    
    Args:
        path: Path to state file
        allow_backup: If True, fallback to .bak file if main file is corrupted
    
    Returns:
        Parsed state dictionary
    
    Raises:
        StateIOError: If file cannot be loaded (and no valid backup)
    """
    errors = []
    
    # Try main file first
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            errors.append(f"Main file error: {e}")
    
    # Try backup file if allowed
    if allow_backup:
        backup_path = path + ".bak"
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                # Note: We recovered from backup but don't auto-save to main
                return state
            except (json.JSONDecodeError, IOError) as e:
                errors.append(f"Backup file error: {e}")
    
    # If we get here, both failed
    error_msg = "; ".join(errors) if errors else f"File not found: {path}"
    raise StateIOError(error_msg)


def save_state(state: Dict[str, Any], path: str, 
               create_backup: bool = True,
               atomic: bool = True) -> None:
    """
    Save state to JSON file with atomic write and optional backup.
    
    Args:
        state: State dictionary to save
        path: Path to state file
        create_backup: If True, create .bak backup before overwriting
        atomic: If True, use atomic write (write to .tmp then rename)
    
    Raises:
        StateIOError: If save fails
    """
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        
        # Create backup of existing file
        if create_backup and os.path.exists(path):
            backup_path = path + ".bak"
            shutil.copy2(path, backup_path)
        
        if atomic:
            # Atomic write: write to temp file, then rename
            tmp_path = path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            # Atomic replace (os.replace is atomic on POSIX and Windows)
            os.replace(tmp_path, path)
        else:
            # Direct write (not atomic)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                
    except Exception as e:
        raise StateIOError(f"Failed to save state: {e}")


def state_exists(path: str) -> bool:
    """Check if state file exists (main or backup)."""
    return os.path.exists(path) or os.path.exists(path + ".bak")


# ============================================================
# Math Utilities
# ============================================================

def clamp(value: float, dim: str, 
          dim_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> float:
    """
    Clamp value to valid range for a dimension.
    
    Args:
        value: Value to clamp
        dim: Dimension name
        dim_ranges: Optional custom ranges (defaults to standard 10-dim ranges)
    
    Returns:
        Clamped value
    """
    if dim_ranges is None:
        # Standard 10-dim ranges
        dim_ranges = {
            "valence": (-1, 1), "arousal": (-1, 1), "dominance": (-1, 1),
            "affiliation": (0, 1), "confidence": (0, 1), "curiosity": (0, 1),
            "frustration": (0, 1), "care": (0, 1), "fatigue": (0, 1), "fulfillment": (0, 1)
        }
    
    lo, hi = dim_ranges.get(dim, (-1, 1))
    return max(lo, min(hi, value))


def clamp_dict(dims: Dict[str, float],
               dim_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> Dict[str, float]:
    """Clamp all values in a dimensions dict."""
    return {k: clamp(v, k, dim_ranges) for k, v in dims.items()}


# ============================================================
# Error Output Utilities
# ============================================================

def print_json_error(message: str, details: Optional[Dict] = None, 
                     exit_code: int = 1) -> None:
    """Print a structured JSON error and exit."""
    output = {"error": message, "success": False}
    if details:
        output.update(details)
    print(json.dumps(output, ensure_ascii=False), file=sys.stderr)
    sys.exit(exit_code)


def print_json_success(data: Dict[str, Any]) -> None:
    """Print a structured JSON success response."""
    output = {"success": True}
    output.update(data)
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ============================================================
# Configuration Loading
# ============================================================

def load_persona_config(skill_dir: str, persona_name: str) -> Optional[Dict[str, Any]]:
    """
    Load persona configuration from JSON file.
    
    Args:
        skill_dir: Path to skill directory
        persona_name: Name of persona preset
    
    Returns:
        Config dict or None if not found
    """
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
                return json.load(f)
        except Exception:
            return None
    return None


def load_safety_boundaries(skill_dir: str) -> Optional[Dict[str, Any]]:
    """Load safety boundaries configuration."""
    path = os.path.join(skill_dir, "config", "safety-boundaries.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_relationship_stages(skill_dir: str) -> Optional[Dict[str, Any]]:
    """Load relationship stages configuration."""
    path = os.path.join(skill_dir, "config", "relationship-stages.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_skill_dir_from_script() -> str:
    """Get skill directory from the calling script's location."""
    # This assumes the script is in scripts/ subdirectory
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.dirname(script_dir)
