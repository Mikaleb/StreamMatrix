# tests/conftest.py
import os
import sys
import types

# Ensure `src/` is importable so `streammatrix` resolves in tests
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Provide a very lightweight stub for the `globals` module used throughout the app.
# This avoids importing the real `globals.py`, which in turn pulls in heavy
# dependencies and introduces circular imports (e.g. via HelperMethods).
if "globals" not in sys.modules:
    gl = types.SimpleNamespace()

    # Match the real module's public surface only as needed for tests,
    # keeping everything minimal and side‑effect free.
    gl.IS_MAC = False  # Linux test environment

    # Basic paths / config used in a few places; safe fallbacks for tests.
    gl.DATA_PATH = os.getcwd()
    gl.top_level_dir = SRC_DIR

    # Managers and singletons that are sometimes accessed at import time.
    # Default to simple namespaces with no‑op methods so tests can inject
    # richer fakes where needed (e.g. `gl.settings_manager` in tests).
    gl.settings_manager = types.SimpleNamespace(
        get_app_settings=lambda: {},
        save_app_settings=lambda *_args, **_kwargs: None,
    )
    gl.deck_manager = types.SimpleNamespace(
        deck_controller=[],
        connect_new_decks=lambda: None,
        remove_controller=lambda *_a, **_k: None,
        close_all=lambda: None,
        stop_usb_monitoring=lambda: None,
    )
    gl.plugin_manager = types.SimpleNamespace(
        get_action_holder_from_id=lambda *_a, **_k: None,
        get_plugin_id_from_action_id=lambda *_a, **_k: "",
        get_is_plugin_out_of_date=lambda *_a, **_k: False,
        loop_daemon=True,
        get_plugin_by_id=lambda *_a, **_k: None,
    )
    gl.page_manager = types.SimpleNamespace(
        get_page_data=lambda *_a, **_k: {},
        update_dict_of_pages_with_path=lambda *_a, **_k: None,
        find_matching_page_path=lambda *_a, **_k: None,
        get_best_page_path_match_from_name=lambda *_a, **_k: None,
        get_page=lambda *_a, **_k: None,
        get_pages=lambda: [],
    )
    gl.tray_icon = types.SimpleNamespace(stop=lambda: None)
    gl.signal_manager = types.SimpleNamespace(trigger_signal=lambda *_a, **_k: None)

    # Misc attributes the app code expects to exist.
    gl.app = None
    gl.threads_running = True
    gl.app_loading_finished_tasks = []
    gl.showed_donate_window = False

    sys.modules["globals"] = gl

