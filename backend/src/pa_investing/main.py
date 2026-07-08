from fastapi import FastAPI

from pa_investing.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="PA Investing Backend")
    app.include_router(router)
    return app


app = create_app()
