"""One persisted recovery pass, shared by the local loop and private HTTP entry.

No AI calls, task administration, credentials discovery, or recursive retry.
Each existing operation retains its own transactional/idempotent checkpoint.
"""

from backend_a.tasks import dispatch_outbox, purge_sent_outbox


def maintenance_once(game):
    purge_sent_outbox(game.store)
    dispatch_outbox(game.store, game.tasks)
    game.recover_job_progress()
    game.recover_job_execution()
    game.cleanup()
