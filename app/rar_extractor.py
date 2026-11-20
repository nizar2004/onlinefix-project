"""Port of RarExtractor.php."""
from __future__ import annotations

import os
import re
from typing import Optional

from . import dialogs, i18n, runtime
from .files_worker import get_third_party
from .process_util import run
from .runtime import log_error, log_info, log_warn, ui_call


class RarExtractor:
    def __init__(self):
        self.std_err = ""
        self.std_out: list[str] = []

    def get_rar_content(self, file: str, password: Optional[str] = None):
        log_info(f"Trying to read {file}")
        files = self.execute_unrar(file, password)
        log_info(f"{file} readed successfully!")
        return files

    def unpack_rar(self, file: str, path: str, password: Optional[str] = None):
        log_info(f"Trying to unpack {file} to {path}")
        self.execute_unrar(file, password, path)
        log_info(f"{file} successfully unpacked to {path}")

    def execute_unrar(self, file: str, password: Optional[str] = None,
                      path: Optional[str] = None):
        self.std_err = ""
        self.std_out = []
        unrar = get_third_party("unrar")
        if not unrar:
            raise RuntimeError("unrar not found")

        args = [unrar, "-p-" if password is None else f"-p{password}", "-y",
                "lb" if path is None else "x", file]
        result = run(args, cwd=path)
        self.std_out = [line for line in (result.stdout or "").splitlines() if line]
        self.std_err = result.stderr or ""

        if "Incorrect password for" in self.std_err:
            if password is None:
                log_warn("Incorrect password. Current password is null, so trying with online-fix.me")
                return self.execute_unrar(file, "online-fix.me", path)
            log_error(f"Incorrect password for {file}")
            raise IOError("Incorrect password")

        if "Cannot open" in self.std_err:
            parent = os.path.dirname(file)
            base = os.path.splitext(os.path.basename(file))[0]
            parts = []
            try:
                for name in os.listdir(parent):
                    if ".part" in name and ".rar" in name and base in name:
                        parts.append(os.path.join(parent, name))
            except OSError:
                parts = []
            parts.sort()

            if not os.path.isfile(file) and parts:
                log_info("Multipart archive detected")
                if path is None:
                    files: list[str] = []
                    for part in parts:
                        log_info(f"Trying to read {part}")
                        files.extend(self.execute_unrar(part, password) or [])
                    log_info("Readed all parts")
                    return files
                self.execute_unrar(parts[0], password, path)
            else:
                raise RuntimeError(self.std_err)

        if path is None:
            return self.std_out
        return None

    def retry_with_ensure_error(self, catched_message: str, file: str,
                                path: Optional[str] = None):
        if catched_message == "Incorrect password" and ui_call(lambda: dialogs.confirm(
                runtime.get_root(), i18n._("RAREXTRACTOR.FAILDEFPASSWD"))):
            password = ui_call(lambda: dialogs.ask_string(
                runtime.get_root(), i18n._("RAREXTRACTOR.PASSWD")))
            if password is None:
                return None
            try:
                if path is None:
                    return self.get_rar_content(file, password)
                self.unpack_rar(file, path, password)
                return True
            except Exception:
                runtime.ui_later(lambda: dialogs.show_message(
                    runtime.get_root(), i18n._("RAREXTRACTOR.FAILPASSWD"), "ERROR"))
                return None
        else:
            msg = catched_message or i18n._("RAREXTRACTOR.FAIL")
            runtime.ui_later(lambda: dialogs.show_message(runtime.get_root(), msg, "ERROR"))
            return None
