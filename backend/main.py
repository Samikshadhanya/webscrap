import logging
import os
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.responses import Response

from services.fbref_service import FBrefService, FBrefServiceError, TeamNotFoundError
from utils.csv_export import team_stats_to_csv
from utils.rate_limit import RateLimiter


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("football-analytics")

app = FastAPI(
    title="Football Analytics CSV API",
    description="Scrapes FBref team data and returns analytics-ready JSON or CSV.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

rate_limiter = RateLimiter(max_requests=30, window_seconds=60)
fbref_service = FBrefService()


@app.middleware("http")
async def rate_limit_requests(request: Request, call_next):
    client_host = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_host):
        logger.warning("Rate limit exceeded for %s", client_host)
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Please try again later."},
        )
    return await call_next(request)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/team")
def get_team(
    name: Annotated[str, Query(min_length=2, max_length=80)],
    season: Annotated[int, Query(ge=1992, le=2100)],
):
    try:
        return fbref_service.get_team_stats(name=name, season=season).model_dump(by_alias=True)
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FBrefServiceError as exc:
        logger.exception("FBref service failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/team/csv")
def get_team_csv(
    name: Annotated[str, Query(min_length=2, max_length=80)],
    season: Annotated[int, Query(ge=1992, le=2100)],
):
    try:
        stats = fbref_service.get_team_stats(name=name, season=season)
        csv_data = team_stats_to_csv(stats)
        filename = f"{stats.team.lower().replace(' ', '-')}-{season}-stats.csv"
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except TeamNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FBrefServiceError as exc:
        logger.exception("CSV generation failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/admin/refresh-season")
def refresh_season(
    background_tasks: BackgroundTasks,
    season: Annotated[int, Query(ge=1992, le=2100)],
    admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
):
    expected_token = os.getenv("ADMIN_REFRESH_TOKEN")
    if expected_token and admin_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")

    background_tasks.add_task(fbref_service.refresh_season, season)
    return {"status": "queued", "season": season}


@app.post("/admin/refresh-season-now")
def refresh_season_now(
    season: Annotated[int, Query(ge=1992, le=2100)],
    admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
):
    expected_token = os.getenv("ADMIN_REFRESH_TOKEN")
    if expected_token and admin_token != expected_token:
        raise HTTPException(status_code=401, detail="Invalid admin token.")

    try:
        return fbref_service.refresh_season(season)
    except FBrefServiceError as exc:
        logger.exception("Season refresh failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
