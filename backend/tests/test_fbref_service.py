import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.fbref_service import FBrefService


def test_team_stats_from_fbref_shaped_tables():
    service = FBrefService()
    service._fetch_html = lambda _url: """
    <table>
      <thead>
        <tr>
          <th>Squad</th><th>Comp</th><th>MP</th><th>W</th><th>D</th><th>L</th>
          <th>GF</th><th>GA</th><th>GD</th><th>xG</th><th>xGA</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Arsenal</td><td>Premier League</td><td>38</td><td>24</td><td>8</td><td>6</td>
          <td>75</td><td>34</td><td>41</td><td>72.3</td><td>35.1</td>
        </tr>
      </tbody>
    </table>
    <table>
      <thead><tr><th>Squad</th><th>Sh</th><th>SoT</th></tr></thead>
      <tbody><tr><td>Arsenal</td><td>600</td><td>210</td></tr></tbody>
    </table>
    <table>
      <thead><tr><th>Squad</th><th>Poss</th></tr></thead>
      <tbody><tr><td>Arsenal</td><td>58.2</td></tr></tbody>
    </table>
    """

    stats = service.get_team_stats("Arsenal", 2025).model_dump(by_alias=True)

    assert stats["team"] == "Arsenal"
    assert stats["matches"] == 38
    assert stats["wins"] == 24
    assert stats["shots_on_target"] == 210
