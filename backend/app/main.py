import os
from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import claude, riot, mental, meta
from app.services.rag_service import warm_index_async

@asynccontextmanager
async def lifespan(app: FastAPI):
    warm_index_async()  # build the RAG index in the background instead of on the first request
    yield

app = FastAPI(title="Valorant AI Companion", version="1.0.0", lifespan=lifespan)

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(claude.router)
app.include_router(riot.router)
app.include_router(mental.router)
app.include_router(meta.router)

@app.get("/")
def root():
    return {"message": "Valorant AI Companion API is running 🚀"}
