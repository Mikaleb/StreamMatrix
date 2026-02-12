from __future__ import annotations

import statistics
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, cast

from StreamDeck.Devices import StreamDeck
from gi.repository import GLib

from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PageManagement.Page import Page

import globals as gl

if TYPE_CHECKING:
    from src.backend.DeckManagement.DeckController import DeckController
    from src.windows.mainWindow.elements.DeckStackChild import DeckStackChild


@dataclass
class MediaPlayerTask:
    deck_controller: "DeckController"
    page: Page
    _callable: callable
    args: tuple
    kwargs: dict

    def run(self) -> None:
        self._callable(*self.args, **self.kwargs)


@dataclass
class MediaPlayerSetTouchscreenImageTask:
    deck_controller: "DeckController"
    page: Page
    native_image: bytes

    n_failed_in_row: ClassVar[dict] = {}

    def run(self) -> None:
        if not self.deck_controller.deck.is_touch():
            return
        try:
            touchscreen_size = self.deck_controller.get_touchscreen_image_size()
            # Maybe avoid to always merge the dial images before applying it
            self.deck_controller.deck.set_touchscreen_image(
                self.native_image,
                x_pos=0,
                y_pos=0,
                width=touchscreen_size[0],
                height=touchscreen_size[1],
            )
            self.native_image = None
            del self.native_image
            MediaPlayerSetTouchscreenImageTask.n_failed_in_row = 0
        except StreamDeck.TransportError as e:
            from loguru import logger as log

            log.error(f"Failed to set deck touchscreen image. Error: {e}")
            MediaPlayerSetTouchscreenImageTask.n_failed_in_row += 1
            if MediaPlayerSetTouchscreenImageTask.n_failed_in_row > 5:
                log.debug(
                    "Failed to set touchscreen image for 5 times "
                    f"in a row for deck {self.deck_controller.serial_number()}. "
                    "Removing controller",
                )

                self.deck_controller.deck.close()
                # Set stop flag - otherwise remove_controller will wait until this
                # task is done, which it never will because it waits
                self.deck_controller.media_player.running = False
                gl.deck_manager.remove_controller(self.deck_controller)

                gl.deck_manager.connect_new_decks()


@dataclass
class MediaPlayerSetImageTask:
    deck_controller: "DeckController"
    page: Page
    key_index: int
    native_image: bytes

    n_failed_in_row: ClassVar[dict] = {}

    def run(self) -> None:
        from loguru import logger as log

        try:
            self.deck_controller.deck.set_key_image(self.key_index, self.native_image)
            self.native_image = None
            del self.native_image
            MediaPlayerSetImageTask.n_failed_in_row[
                self.deck_controller.serial_number()
            ] = 0
        except StreamDeck.TransportError as e:
            log.error(f"Failed to set deck key image. Error: {e}")

            beta_resume = (
                gl.settings_manager.get_app_settings()
                .get("system", {})
                .get("beta-resume-mode", True)
            )
            if beta_resume:
                return

            MediaPlayerSetImageTask.n_failed_in_row[
                self.deck_controller.serial_number()
            ] += 1
            if (
                MediaPlayerSetImageTask.n_failed_in_row[
                    self.deck_controller.serial_number()
                ]
                > 5
            ):
                log.debug(
                    "Failed to set key_image for 5 times "
                    f"in a row for deck {self.deck_controller.serial_number()}. "
                    "Removing controller",
                )

                self.deck_controller.deck.close()
                # Set stop flag - otherwise remove_controller will wait until this
                # task is done, which it never will because it waits
                self.deck_controller.media_player.running = False
                gl.deck_manager.remove_controller(self.deck_controller)

                gl.deck_manager.connect_new_decks()


class MediaPlayerThread(threading.Thread):
    """
    Dedicated media player loop for a single deck.

    Handles background video updates, per-input media ticks and queued image
    updates, keeping this logic out of the main DeckController.
    """

    def __init__(self, deck_controller: "DeckController") -> None:
        super().__init__(name="MediaPlayerThread", daemon=True)
        self.deck_controller: DeckController = deck_controller
        # Max refresh rate of the internal displays
        self.FPS = 30

        self.running = False
        self.media_ticks = 0

        self.pause = False
        self._stop = False

        self.tasks: list[MediaPlayerTask] = []
        self.image_tasks: dict[int, MediaPlayerSetImageTask] = {}
        self.touchscreen_task: MediaPlayerSetTouchscreenImageTask | None = None

        self.fps: list[float] = []
        self.old_warning_state = False

        self.show_fps_warnings = (
            gl.settings_manager.get_app_settings()
            .get("warnings", {})
            .get("enable-fps-warnings", True)
        )

    def run(self) -> None:  # noqa: D401
        """Thread main loop."""
        self.running = True

        while True:
            start = time.time()

            if not self.pause:
                if self.deck_controller.background.video is not None:
                    if (
                        self.deck_controller.background.video.page
                        is self.deck_controller.active_page
                    ):
                        # There is a background video
                        video_each_nth_frame = (
                            self.FPS // self.deck_controller.background.video.fps
                        )
                        if self.media_ticks % video_each_nth_frame == 0:
                            self.deck_controller.background.update_tiles()

                # TODO: generalize
                for key in self.deck_controller.inputs[Input.Key]:
                    cast("ControllerKey", key).on_media_player_tick()

                for dial in self.deck_controller.inputs[Input.Dial]:
                    cast("ControllerDial", dial).on_media_player_tick()

                # Perform media player tasks
                self.perform_media_player_tasks()

            self.media_ticks += 1

            # Wait for approximately 1/30th of a second before the next call
            end = time.time()
            self.append_fps(1 / (end - start))
            self.update_low_fps_warning()
            wait = max(0, 1 / self.FPS - (end - start))
            time.sleep(wait)

            if self._stop:
                break

        self.running = False

    def append_fps(self, fps: float) -> None:
        self.fps.append(fps)
        if len(self.fps) > self.FPS * 2:
            self.fps.pop(0)

    def get_median_fps(self) -> float:
        return statistics.median(self.fps)

    def update_low_fps_warning(self) -> None:
        if not self.show_fps_warnings:
            return

        show_warning = self.get_median_fps() < self.FPS * 0.8
        if self.old_warning_state == show_warning:
            return
        self.old_warning_state = show_warning

        self.set_banner_revealed(show_warning)

    def set_show_fps_warnings(self, state: bool) -> None:
        self.show_fps_warnings = state
        if state:
            self.old_warning_state = False
        else:
            self.set_banner_revealed(False)

    def set_banner_revealed(self, state: bool) -> None:
        deck_stack_child: "DeckStackChild" = (
            self.deck_controller.get_own_deck_stack_child()
        )
        if deck_stack_child is None:
            return

        GLib.idle_add(deck_stack_child.low_fps_banner.set_revealed, state)

    def stop(self) -> None:
        self._stop = True
        while self.running:
            time.sleep(0.1)

    def add_task(self, method: callable, *args, **kwargs) -> None:
        self.tasks.append(
            MediaPlayerTask(
            deck_controller=self.deck_controller,
            page=self.deck_controller.active_page,
            _callable=method,
            args=args,
            kwargs=kwargs,
        )
        )

    def add_touchscreen_task(self, native_image: bytes) -> None:
        self.touchscreen_task = MediaPlayerSetTouchscreenImageTask(
            deck_controller=self.deck_controller,
            page=self.deck_controller.active_page,
            native_image=native_image,
        )

    def add_image_task(self, key_index: int, native_image: bytes) -> None:
        self.image_tasks[key_index] = MediaPlayerSetImageTask(
            deck_controller=self.deck_controller,
            page=self.deck_controller.active_page,
            key_index=key_index,
            native_image=native_image,
        )

    def perform_media_player_tasks(self) -> None:
        for task in self.tasks.copy():
            if task.page is self.deck_controller.active_page:
                task.run()

            try:
                self.tasks.remove(task)
            except ValueError:
                pass

        for key in list(self.image_tasks.keys()):
            try:
                self.image_tasks[key].run()
                del self.image_tasks[key]
            except KeyError:
                pass

        if self.touchscreen_task is not None:
            self.touchscreen_task.run()
            del self.touchscreen_task
            self.touchscreen_task = None

    def check_connection(self) -> None:
        from loguru import logger as log

        try:
            self.deck_controller.deck.get_firmware_version()
        except StreamDeck.TransportError as e:
            log.error(f"Seams like the deck is not connected. Error: {e}")
            MediaPlayerSetImageTask.n_failed_in_row[
                self.deck_controller.serial_number()
            ] += 1
            if (
                MediaPlayerSetImageTask.n_failed_in_row[
                    self.deck_controller.serial_number()
                ]
                > 5
            ):
                log.debug(
                    "Failed to contact the deck 5 times in a row: "
                    f"{self.deck_controller.serial_number()}. Removing controller",
                )

                self.deck_controller.deck.close()
                # Set stop flat - otherwise remove_controller will wait until this
                # task is done, which it never will because it waits
                self.deck_controller.media_player.running = False
                gl.deck_manager.remove_controller(self.deck_controller)

                gl.deck_manager.connect_new_decks()

