import logging
import os
import random
import re
import time
from dataclasses import dataclass
from io import StringIO
from typing import Any

import pandas as pd
import requests
from bs4 import BeautifulSoup, Comment
from models.team import TeamStats
from utils.persistent_cache import PersistentCache


logger = logging.getLogger(__name__)


class FBrefServiceError(Exception):
    pass


class TeamNotFoundError(FBrefServiceError):
    pass


@dataclass
class CacheEntry:
    value: TeamStats
    expires_at: float


class FBrefService:
    BASE_URL = "https://fbref.com"
    BIG_FIVE_URL = (
        "https://fbref.com/en/comps/Big5/{season_slug}/stats/squads/"
        "{season_slug}-Big-5-European-Leagues-Stats"
    )
    CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", str(60 * 60 * 24)))
    MIN_REQUEST_INTERVAL_SECONDS = float(os.getenv("FBREF_MIN_REQUEST_INTERVAL_SECONDS", "8"))
    MAX_RETRIES = int(os.getenv("FBREF_MAX_RETRIES", "3"))

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], CacheEntry] = {}
        self._last_request_at = 0.0
        self._persistent_cache = PersistentCache(
            cache_dir=os.getenv("CACHE_DIR", ".cache/team-stats"),
            ttl_seconds=self.CACHE_TTL_SECONDS,
        )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://fbref.com/",
            }
        )

    def get_team_stats(self, name: str, season: int) -> TeamStats:
        clean_name = self._validate_team_name(name)
        cache_key = (clean_name.casefold(), season)
        cached = self._cache.get(cache_key)
        disk_cache_key = self._cache_key(clean_name, season)

        if cached and cached.expires_at > time.time():
            logger.info("Cache hit for team=%s season=%s", clean_name, season)
            return cached.value

        disk_cached = self._persistent_cache.get(disk_cache_key)
        if disk_cached:
            logger.info("Persistent cache hit for team=%s season=%s", clean_name, season)
            stats = TeamStats(**disk_cached)
            self._cache[cache_key] = CacheEntry(
                value=stats,
                expires_at=time.time() + self.CACHE_TTL_SECONDS,
            )
            return stats

        logger.info("Fetching FBref data for team=%s season=%s", clean_name, season)
        try:
            stats = self._scrape_team_stats(clean_name, season)
        except FBrefServiceError:
            stale_cached = self._persistent_cache.get(disk_cache_key, allow_expired=True)
            if stale_cached:
                logger.warning("Serving stale cache for team=%s season=%s", clean_name, season)
                return TeamStats(**stale_cached)
            raise

        self._store_stats(clean_name, season, stats)
        return stats

    def refresh_season(self, season: int) -> dict[str, int]:
        logger.info("Refreshing FBref season cache for season=%s", season)
        standard, shooting, possession, fixtures = self._scrape_season_tables(season)
        refreshed = 0

        for _, row in standard.iterrows():
            team_name = self._cell(row, "Squad", "")
            if not team_name:
                continue
            stats = self._build_team_stats(row, team_name, season, shooting, possession, fixtures)
            self._store_stats(team_name, season, stats)
            refreshed += 1

        logger.info("Refreshed %s teams for season=%s", refreshed, season)
        return {"season": season, "teams_refreshed": refreshed}

    def _store_stats(self, team_name: str, season: int, stats: TeamStats) -> None:
        cache_key = (team_name.casefold(), season)
        disk_cache_key = self._cache_key(team_name, season)
        self._cache[cache_key] = CacheEntry(
            value=stats,
            expires_at=time.time() + self.CACHE_TTL_SECONDS,
        )
        self._persistent_cache.set(disk_cache_key, stats.model_dump(by_alias=True))

    def _validate_team_name(self, name: str) -> str:
        clean_name = " ".join(name.strip().split())
        if not re.fullmatch(r"[A-Za-z0-9 .'\-&]+", clean_name):
            raise FBrefServiceError("Team name contains unsupported characters.")
        if len(clean_name) < 2:
            raise FBrefServiceError("Team name must be at least 2 characters.")
        return clean_name

    def _scrape_team_stats(self, team_name: str, season: int) -> TeamStats:
        standard, shooting, possession, fixtures = self._scrape_season_tables(season)
        row = self._match_team_row(standard, team_name)
        matched_team = self._cell(row, "Squad", team_name)
        return self._build_team_stats(row, matched_team, season, shooting, possession, fixtures)

    def _scrape_season_tables(
        self,
        season: int,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
        season_slug = self._season_slug(season)
        html = self._fetch_html(self.BIG_FIVE_URL.format(season_slug=season_slug))
        tables = self._read_tables(html)
        standard = self._find_table(tables, required_columns={"Squad", "MP", "W", "D", "L", "GF", "GA"})
        shooting = self._find_table(tables, required_columns={"Squad", "Sh", "SoT"}, required=False)
        possession = self._find_table(tables, required_columns={"Squad", "Poss"}, required=False)

        fixtures = None
        try:
            fixtures = self._fetch_fixtures_table(season)
        except FBrefServiceError:
            logger.warning("Fixture table unavailable for season=%s", season)

        return standard, shooting, possession, fixtures

    def _build_team_stats(
        self,
        row: pd.Series,
        matched_team: str,
        season: int,
        shooting: pd.DataFrame | None,
        possession: pd.DataFrame | None,
        fixtures: pd.DataFrame | None,
    ) -> TeamStats:
        shooting_row = self._optional_team_row(shooting, matched_team)
        possession_row = self._optional_team_row(possession, matched_team)

        matches_played = self._number(row, "MP")
        wins = self._number(row, "W")
        draws = self._number(row, "D")
        losses = self._number(row, "L")
        goals_for = self._number(row, "GF")
        goals_against = self._number(row, "GA")

        return TeamStats(
            team=matched_team,
            competition=self._cell(row, "Comp", "Big 5 European Leagues"),
            season=season,
            matches_played=matches_played,
            wins=wins,
            draws=draws,
            losses=losses,
            goals_scored=goals_for,
            goals_conceded=goals_against,
            goal_difference=self._number(row, "GD", default=goals_for - goals_against),
            xg=self._float(row, "xG"),
            xga=self._float(row, "xGA"),
            possession=self._float(possession_row if possession_row is not None else row, "Poss"),
            shots=self._number(shooting_row if shooting_row is not None else row, "Sh"),
            shots_on_target=self._number(shooting_row if shooting_row is not None else row, "SoT"),
            form=self._get_recent_form_from_table(fixtures, matched_team),
        )

    def _fetch_html(self, url: str) -> str:
        for attempt in range(1, self.MAX_RETRIES + 1):
            self._wait_for_polite_interval()
            try:
                response = self._session.get(url, timeout=25)
                if response.status_code == 403:
                    raise FBrefServiceError(
                        "FBref blocked this request. Cached data will be used when available."
                    )
                if response.status_code == 429:
                    self._sleep_before_retry(attempt)
                    continue
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                if attempt == self.MAX_RETRIES:
                    raise FBrefServiceError("Unable to fetch FBref data right now.") from exc
                self._sleep_before_retry(attempt)

        raise FBrefServiceError("Unable to fetch FBref data right now.")

    def _read_tables(self, html: str) -> list[pd.DataFrame]:
        try:
            tables = pd.read_html(StringIO(html))
        except ValueError as exc:
            commented_html = self._extract_commented_tables(html)
            if not commented_html:
                raise FBrefServiceError("No readable FBref tables were found.") from exc
            try:
                tables = pd.read_html(StringIO(commented_html))
            except ValueError as commented_exc:
                raise FBrefServiceError("No readable FBref tables were found.") from commented_exc

        cleaned_tables = []
        for table in tables:
            if isinstance(table.columns, pd.MultiIndex):
                table.columns = [column[-1] for column in table.columns]
            cleaned_tables.append(table)
        return cleaned_tables

    def _find_table(
        self,
        tables: list[pd.DataFrame],
        required_columns: set[str],
        required: bool = True,
    ) -> pd.DataFrame | None:
        for table in tables:
            if required_columns.issubset(set(map(str, table.columns))):
                return table
        if required:
            raise FBrefServiceError(f"FBref table missing columns: {', '.join(sorted(required_columns))}")
        return None

    def _match_team_row(self, table: pd.DataFrame, team_name: str) -> pd.Series:
        normalized_target = self._normalize(team_name)
        candidates = table[table["Squad"].astype(str).map(self._normalize).str.contains(normalized_target, regex=False)]
        if candidates.empty:
            all_teams = table["Squad"].dropna().astype(str).tolist()
            close = [team for team in all_teams if normalized_target in self._normalize(team)]
            if close:
                candidates = table[table["Squad"].isin(close)]

        if candidates.empty:
            raise TeamNotFoundError(f"No FBref team found for '{team_name}' in the selected season.")
        return candidates.iloc[0]

    def _optional_team_row(self, table: pd.DataFrame | None, team_name: str) -> pd.Series | None:
        if table is None or "Squad" not in table.columns:
            return None
        normalized_target = self._normalize(team_name)
        candidates = table[table["Squad"].astype(str).map(self._normalize).str.contains(normalized_target, regex=False)]
        return None if candidates.empty else candidates.iloc[0]

    def _get_recent_form(self, team_name: str, season: int) -> str:
        try:
            fixture_table = self._fetch_fixtures_table(season)
            return self._get_recent_form_from_table(fixture_table, team_name)
        except FBrefServiceError:
            logger.warning("Recent form unavailable for %s %s", team_name, season)
            return "N/A"

    def _fetch_fixtures_table(self, season: int) -> pd.DataFrame | None:
        season_slug = self._season_slug(season)
        fixtures_url = (
            f"{self.BASE_URL}/en/comps/Big5/{season_slug}/schedule/"
            f"{season_slug}-Big-5-European-Leagues-Scores-and-Fixtures"
        )
        html = self._fetch_html(fixtures_url)
        tables = self._read_tables(html)
        return self._find_table(tables, required_columns={"Home", "Away", "Score"}, required=False)

    def _get_recent_form_from_table(self, fixture_table: pd.DataFrame | None, team_name: str) -> str:
        if fixture_table is None:
            return "N/A"

        team_rows = fixture_table[
            (fixture_table["Home"].astype(str).map(self._normalize) == self._normalize(team_name))
            | (fixture_table["Away"].astype(str).map(self._normalize) == self._normalize(team_name))
        ].copy()
        team_rows = team_rows.dropna(subset=["Score"])
        form = []
        for _, match in team_rows.tail(5).iterrows():
            result = self._result_from_score(match, team_name)
            if result:
                form.append(result)
        return "".join(form) if form else "N/A"

    def _result_from_score(self, match: pd.Series, team_name: str) -> str | None:
        score = str(match.get("Score", ""))
        score_match = re.search(r"(\d+)\D+(\d+)", score)
        if not score_match:
            return None

        home_goals, away_goals = map(int, score_match.groups())
        is_home = self._normalize(str(match.get("Home", ""))) == self._normalize(team_name)
        team_goals, opponent_goals = (home_goals, away_goals) if is_home else (away_goals, home_goals)
        if team_goals > opponent_goals:
            return "W"
        if team_goals < opponent_goals:
            return "L"
        return "D"

    def _cell(self, row: pd.Series | None, column: str, default: str) -> str:
        if row is None or column not in row or pd.isna(row[column]):
            return default
        return str(row[column])

    def _number(self, row: pd.Series | None, column: str, default: int = 0) -> int:
        value = self._value(row, column)
        if value is None:
            return default
        try:
            return int(float(str(value).replace(",", "")))
        except ValueError:
            return default

    def _float(self, row: pd.Series | None, column: str, default: float | None = None) -> float | None:
        value = self._value(row, column)
        if value is None:
            return default
        try:
            return round(float(str(value).replace("%", "").replace(",", "")), 2)
        except ValueError:
            return default

    def _value(self, row: pd.Series | None, column: str) -> Any:
        if row is None or column not in row or pd.isna(row[column]):
            return None
        return row[column]

    def _normalize(self, value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()

    def _cache_key(self, team_name: str, season: int) -> str:
        return f"{self._normalize(team_name).replace(' ', '-')}-{season}"

    def _season_slug(self, season: int) -> str:
        return f"{season - 1}-{season}"

    def _extract_commented_tables(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        return "\n".join(
            str(comment)
            for comment in soup.find_all(string=lambda text: isinstance(text, Comment))
            if "<table" in str(comment)
        )

    def _wait_for_polite_interval(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.MIN_REQUEST_INTERVAL_SECONDS:
            time.sleep(self.MIN_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_at = time.time()

    def _sleep_before_retry(self, attempt: int) -> None:
        delay = min(30, (2**attempt) + random.uniform(0.5, 2.0))
        logger.info("Waiting %.1f seconds before retrying FBref request", delay)
        time.sleep(delay)
