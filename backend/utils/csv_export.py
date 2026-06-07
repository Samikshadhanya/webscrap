import csv
import io

from models.team import TeamStats


def team_stats_to_csv(stats: TeamStats) -> str:
    output = io.StringIO()
    fieldnames = [
        "team",
        "competition",
        "season",
        "matches",
        "wins",
        "draws",
        "losses",
        "goals_scored",
        "goals_conceded",
        "goal_difference",
        "xg",
        "xga",
        "possession",
        "shots",
        "shots_on_target",
        "form",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerow(stats.model_dump(by_alias=True))
    return output.getvalue()
