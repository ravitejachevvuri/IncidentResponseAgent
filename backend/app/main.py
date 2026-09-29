import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import OperationalError

from app.db import Base, engine, SessionLocal
from app.api.routes import router
from app.models import models  # noqa: F401 ensure models are registered on Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Production Memory", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


def _wait_for_db(retries: int = 20, delay_seconds: float = 1.5):
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with engine.connect():
                return
        except OperationalError as e:
            last_error = e
            logger.info("Database not ready yet (attempt %s/%s): %s", attempt, retries, str(e)[:300])
            time.sleep(delay_seconds)
    raise RuntimeError("Database did not become available in time") from last_error


@app.on_event("startup")
def on_startup():
    _wait_for_db()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        from app.models.models import Incident
        from seed.seed_data import reset_and_seed

        if db.query(Incident).count() == 0:
            reset_and_seed(db)
    finally:
        db.close()

