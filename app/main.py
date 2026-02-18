import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.routes import router
from app.config import BASE_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting MedAgent AI - initializing services...")
    from app.services.rag_service import get_rag_service
    get_rag_service()
    logger.info("RAG service ready")
    yield
    logger.info("Shutting down MedAgent AI")


app = FastAPI(
    title="MedAgent AI",
    description=(
        "GenAI-powered Clinical Decision Support System. "
        "Analyzes symptoms, vitals, lab reports, and medical history "
        "to provide differential diagnoses with confidence scores."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "MedAgent AI API is running. Visit /docs for API documentation."}
