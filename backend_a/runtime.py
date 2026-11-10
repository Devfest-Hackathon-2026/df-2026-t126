"""Runtime construction is the sole place allowed to create cloud clients.

Default startup is completely offline, regardless of installed credentials.
"""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from backend_a.auth import DenyInternalAuth, FirebaseAuth, GoogleInternalAuth, LocalAuth
from backend_a.game import GameService
from backend_a.store import FirestoreStore, MemoryStore
from backend_a.tasks import CloudTasks, MemoryTasks
from common.settings import Settings
from common.storage import AssetStorage, GoogleBlobs, MemoryBlobs


@dataclass
class Runtime:
    game: GameService
    auth: object
    internal_auth: object
    settings: Settings


def localhost_endpoint(value):
    parsed = urlsplit(value if "://" in value else f"http://{value}")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or not parsed.port:
        raise ValueError("Emulator endpoint must be an explicit loopback host:port")
    return parsed


def build_runtime(settings=None):
    settings = settings or Settings()
    if settings.runtime_mode == "cloud" and any(
        os.environ.get(name)
        for name in (
            "FIRESTORE_EMULATOR_HOST",
            "FIREBASE_AUTH_EMULATOR_HOST",
            "STORAGE_EMULATOR_HOST",
            "FIREBASE_STORAGE_EMULATOR_HOST",
        )
    ):
        raise ValueError("Cloud runtime must not inherit emulator authentication/endpoints")
    if settings.runtime_mode == "local":
        store, blobs, sender, auth = MemoryStore(), MemoryBlobs(), MemoryTasks(), LocalAuth()
        internal_auth = DenyInternalAuth()
    else:
        import firebase_admin
        from google.cloud import firestore, storage

        if settings.runtime_mode == "emulator":
            # All services needed below must be present; no fallback to real services.
            for env in ("FIRESTORE_EMULATOR_HOST", "FIREBASE_AUTH_EMULATOR_HOST"):
                localhost_endpoint(os.environ.get(env, ""))
            from google.auth.credentials import AnonymousCredentials

            credentials = AnonymousCredentials()
            client = firestore.Client(project=settings.project_id, credentials=credentials)
            blobs, sender, internal_auth = MemoryBlobs(), MemoryTasks(), DenyInternalAuth()
            storage_host = os.environ.get("FIREBASE_STORAGE_EMULATOR_HOST") or os.environ.get(
                "STORAGE_EMULATOR_HOST"
            )
            if storage_host:
                endpoint = localhost_endpoint(storage_host)
                other = os.environ.get("STORAGE_EMULATOR_HOST")
                if other and localhost_endpoint(other).netloc != endpoint.netloc:
                    raise ValueError("Storage emulator endpoints must agree")
                client_storage = storage.Client(
                    project=settings.project_id,
                    credentials=credentials,
                    client_options={"api_endpoint": f"http://{endpoint.netloc}"},
                    use_auth_w_custom_endpoint=False,
                )
                blobs = GoogleBlobs(
                    client_storage.bucket(
                        settings.bucket_name or f"{settings.project_id}.appspot.com"
                    )
                )

            # Firebase Admin uses unsigned emulator tokens only with this env set.
            class EmulatorCredential(firebase_admin.credentials.Base):
                def get_credential(self):
                    return credentials

            app = firebase_admin.initialize_app(
                EmulatorCredential(),
                options={"projectId": settings.project_id},
                name=f"a-{os.urandom(8).hex()}",
            )
        else:
            from google.cloud import tasks_v2

            required = [
                settings.bucket_name,
                settings.tasks_location,
                settings.tasks_queue,
                settings.worker_url,
                settings.deadline_url,
                settings.tasks_service_account,
                settings.internal_audience,
            ]
            if not all(required):
                raise ValueError(
                    "Cloud mode requires explicit storage/tasks/internal-auth settings"
                )
            client = firestore.Client(project=settings.project_id)
            blobs = GoogleBlobs(
                storage.Client(project=settings.project_id).bucket(settings.bucket_name)
            )
            sender = CloudTasks(tasks_v2.CloudTasksClient(), settings)
            app = firebase_admin.initialize_app(
                options={"projectId": settings.project_id}, name=f"a-{os.urandom(8).hex()}"
            )
            internal_auth = GoogleInternalAuth(
                settings.internal_audience, settings.tasks_service_account
            )
        store, auth = FirestoreStore(client), FirebaseAuth(app)
    assets = AssetStorage(store, blobs)
    game = GameService(store, assets, sender, settings)
    return Runtime(game, auth, internal_auth, settings)
