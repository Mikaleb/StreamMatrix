from src.backend.DeckManagement.DeckController import DeckController


class DummyDeck:
    def __init__(self, size):
        self._size = size

    def key_image_format(self):
        # Mimic real API: returns dict with "size"
        return {"size": self._size}


def make_controller(size):
    # Bypass __init__ to avoid opening real decks / threads
    controller = DeckController.__new__(DeckController)
    controller.deck = DummyDeck(size)
    # Pretend the deck is alive
    controller.get_alive = lambda: True
    return controller


def test_get_key_image_size_enforces_minimum():
    dc = make_controller((50, 60))  # smaller than 72x72
    width, height = dc.get_key_image_size()
    assert (width, height) == (72, 72)


def test_get_key_image_size_passes_through_larger_values():
    dc = make_controller((100, 120))
    width, height = dc.get_key_image_size()
    assert (width, height) == (100, 120)
