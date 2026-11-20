"""INI storage compatible with DevelNext's IniStorage files."""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from typing import Any, Optional


class IniStorage:
    def __init__(self, path: str, autosave: bool = True):
        self.path = path
        self.autosave = autosave
        self._lock = threading.RLock()
        self._sections: "OrderedDict[str, OrderedDict[str, str]]" = OrderedDict()
        self.load()

    # ---------------------------------------------------------------- parsing
    def load(self):
        with self._lock:
            self._sections = OrderedDict()
            if not os.path.isfile(self.path):
                return
            current: Optional[OrderedDict[str, str]] = None
            last_key: Optional[str] = None
            try:
                with open(self.path, "r", encoding="utf-8-sig", errors="replace") as fh:
                    for raw in fh:
                        line = raw.rstrip("\r\n")
                        stripped = line.strip()
                        if not stripped:
                            continue
                        if stripped.startswith("[") and stripped.endswith("]"):
                            name = stripped[1:-1]
                            current = self._sections.setdefault(name, OrderedDict())
                            last_key = None
                            continue
                        if stripped[0] in ";#" and "=" not in stripped:
                            continue
                        if current is None:
                            current = self._sections.setdefault("", OrderedDict())
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            current[key] = value.strip()
                            last_key = key
                        elif last_key is not None:
                            # continuation of a multi-line value
                            current[last_key] += "\n" + line
            except OSError:
                pass

    def save(self):
        with self._lock:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                first = True
                for name, values in self._sections.items():
                    if not first:
                        fh.write("\n")
                    first = False
                    if name != "":
                        fh.write(f"[{name}]\n")
                    for key, value in values.items():
                        if "\n" in str(value):
                            value = str(value).replace("\n", "\\n")
                        fh.write(f"{key}={value}\n")
            os.replace(tmp, self.path)

    def _maybe_save(self):
        if self.autosave:
            self.save()

    # ----------------------------------------------------------------- access
    def sections(self) -> list[str]:
        return list(self._sections.keys())

    def has_section(self, section: str) -> bool:
        return section in self._sections

    def section(self, section: str) -> dict[str, str]:
        return dict(self._sections.get(section, {}))

    def ensure_section(self, section: str):
        self._sections.setdefault(section, OrderedDict())

    def get(self, key: str, section: str = "User Settings", default: Any = None) -> Any:
        values = self._sections.get(section)
        if not values or key not in values:
            return default
        value = values[key]
        if value == "":
            return default
        return value

    def get_raw(self, key: str, section: str = "User Settings", default: Any = None) -> Any:
        values = self._sections.get(section)
        if not values or key not in values:
            return default
        return values[key]

    def get_bool(self, key: str, section: str = "User Settings", default: bool = False) -> bool:
        raw = self.get_raw(key, section, None)
        if raw is None:
            return default
        return str(raw).strip().lower() in ("1", "true", "yes", "on")

    def get_int(self, key: str, section: str = "User Settings", default: int = 0) -> int:
        raw = self.get(key, section, None)
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value: Any, section: str = "User Settings"):
        with self._lock:
            self.ensure_section(section)
            if isinstance(value, bool):
                value = "1" if value else ""
            elif value is None:
                value = ""
            else:
                value = str(value)
            self._sections[section][key] = value
            self._maybe_save()

    def remove(self, key: str, section: str = "User Settings"):
        with self._lock:
            if section in self._sections:
                self._sections[section].pop(key, None)
                self._maybe_save()

    def put(self, values: dict[str, Any], section: str):
        with self._lock:
            self.ensure_section(section)
            for key, value in values.items():
                if isinstance(value, bool):
                    value = "1" if value else ""
                elif value is None:
                    value = ""
                else:
                    value = str(value)
                self._sections[section][key] = value
            self._maybe_save()

    def remove_section(self, section: str):
        with self._lock:
            self._sections.pop(section, None)
            self._maybe_save()
