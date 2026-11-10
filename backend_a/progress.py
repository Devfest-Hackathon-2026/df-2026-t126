"""Public entry points for the B Worker process; configure at its startup.

No Worker implementation, retry loop or AI logic is owned by this module.
"""

from backend_a.game import GameService

_game = None


def configure_progress(game: GameService):
    global _game
    _game = game


def advance_step(room_id: str, round_id: str) -> None:
    if _game is None:
        raise RuntimeError("configure_progress must be called in the Worker process")
    _game.advance_step(room_id, round_id)


def can_read_asset(uid: str, round_id: str, asset_id: str) -> bool:
    if _game is None:
        raise RuntimeError("configure_progress must be called at process startup")
    return _game.can_read_asset(uid, round_id, asset_id)
