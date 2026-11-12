import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionLocal
from app.errors import ApiError, api_error_handler
from app.routers import auth, business, industries, me

app = FastAPI(title="GrowthCognix API", version="0.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins,
                   allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(ApiError, api_error_handler)


@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["x-request-id"] = request.state.request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {
        "code": "VALIDATION_ERROR", "message": "Some fields need attention.",
        "request_id": request.state.request_id,
        "details": {"fields": [{"loc": e["loc"][1:], "msg": e["msg"]} for e in exc.errors()]}}})


@app.get("/api/v1/health", tags=["system"])
async def health() -> dict:
    async with SessionLocal() as s:
        await s.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


for r in (auth.router, me.router, industries.router, business.router):
    app.include_router(r, prefix="/api/v1")
