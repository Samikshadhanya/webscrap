from pydantic import BaseModel, Field


class TeamStats(BaseModel):
    team: str
    competition: str
    season: int
    matches_played: int = Field(alias="matches")
    wins: int
    draws: int
    losses: int
    goals_scored: int
    goals_conceded: int
    goal_difference: int
    xg: float | None = None
    xga: float | None = None
    possession: float | None = None
    shots: int = 0
    shots_on_target: int = 0
    form: str = "N/A"

    model_config = {
        "populate_by_name": True,
    }
