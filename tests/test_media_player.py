from statistics import median
import globals as gl
from src.backend.DeckManagement.MediaPlayer import MediaPlayerThread


class DummySettingsManager:
    def get_app_settings(self):
        # minimal structure used by MediaPlayerThread.__init__
        return {
            "warnings": {
                "enable-fps-warnings": True,
            }
        }


gl.settings_manager = DummySettingsManager()


def make_thread():
    # deck_controller is only stored, not used by append_fps/get_median_fps
    return MediaPlayerThread(deck_controller=object())


def test_append_fps_truncates_list():
    mp = make_thread()
    for _ in range(mp.FPS * 2 + 10):
        mp.append_fps(30.0)
    assert len(mp.fps) <= mp.FPS * 2


def test_get_median_fps():
    mp = make_thread()
    values = [10.0, 20.0, 30.0]
    for v in values:
        mp.append_fps(v)
    assert mp.get_median_fps() == median(values)
