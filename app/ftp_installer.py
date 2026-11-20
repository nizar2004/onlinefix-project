"""Port of ftpInstaller.php: silent FreeTP installers executed in Proton."""
from __future__ import annotations

import os
import threading

from . import files_worker, i18n, runtime
from .process_util import hook_process_outputs, popen, wait_for_process
from .runtime import GLOBALS, ui_later


def convert_to_windows_path(path: str) -> str:
    return "Z:" + path.replace("/", "\\")


def install(game_name: str, installers: list[str], prefix_path: str,
            install_path: str, remove_after_install: bool):
    app = runtime.get_app()
    main = app.main_form
    panel = main.add_stub_game()
    panel["name"].set_name(game_name)
    panel["status"].set_status(i18n._("INSTALLING"))

    proton = files_worker.get_proton_executable()
    converted = convert_to_windows_path(install_path)
    GLOBALS["implicitDisableReason"] = "ftpInstalling"

    def worker():
        for installer in installers:
            if not installer:
                continue
            os.makedirs(prefix_path, exist_ok=True)
            try:
                process = popen(
                    [proton, "run", installer, f"/DIR={converted}", "/TASKS=", "/SILENT"],
                    cwd=os.path.dirname(installer),
                    env={
                        "STEAM_COMPAT_DATA_PATH": prefix_path,
                        "STEAM_COMPAT_CLIENT_INSTALL_PATH": os.path.join(os.path.expanduser("~"), ".steam", "steam"),
                        "WINEDEBUG": "-all",
                    },
                )
            except Exception as exc:
                runtime.log_error(str(exc))
                ui_later(lambda: _fail(panel, str(exc)))
                return
            hook_process_outputs(process)
            exit_code = wait_for_process(process)
            if exit_code != 0:
                ui_later(lambda code=exit_code: _fail(panel, code))
                import shutil
                shutil.rmtree(prefix_path, ignore_errors=True)
                if GLOBALS.get("implicitDisableReason") == "ftpInstalling":
                    GLOBALS["implicitDisableReason"] = None
                return

        files = files_worker.scan_dir(install_path)

        def finish():
            panel["box"].destroy()
            form = app.show_form("newGameConfigurator", new=True)
            form.game_params["skipConfig"] = True
            form.game_params["originalFile"] = installers[0]
            form.clean_after_add.set_selected(remove_after_install)
            form.game_name_var.set(game_name)
            form.prefix_path_var.set(prefix_path)
            form.prepare_for_game(files, install_path)
            if GLOBALS.get("implicitDisableReason") == "ftpInstalling":
                GLOBALS["implicitDisableReason"] = None

        ui_later(finish)

    threading.Thread(target=worker, daemon=True).start()


def _fail(panel, code):
    from . import dialogs
    dialogs.show_message(runtime.get_root(), i18n._("FTPINSTALLER.FAILED") % code, "ERROR")
    try:
        panel["box"].destroy()
    except Exception:
        pass
