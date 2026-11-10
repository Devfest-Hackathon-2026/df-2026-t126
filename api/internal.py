from api.app import create_app

app = create_app(internal=True, maintenance_endpoint=True)
