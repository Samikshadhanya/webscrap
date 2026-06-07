const API_BASE_URL = window.FOOTBALL_API_URL || "http://127.0.0.1:8000";

const form = document.getElementById("analysis-form");
const teamInput = document.getElementById("team-name");
const seasonSelect = document.getElementById("season");
const statusText = document.getElementById("status");
const statsTable = document.getElementById("stats-table");
const downloadButton = document.getElementById("download-button");
const analyzeButton = document.getElementById("analyze-button");

let currentQuery = null;

const fields = [
  ["team", "Team Name"],
  ["competition", "Competition"],
  ["season", "Season"],
  ["matches", "Matches Played"],
  ["wins", "Wins"],
  ["draws", "Draws"],
  ["losses", "Losses"],
  ["goals_scored", "Goals Scored"],
  ["goals_conceded", "Goals Conceded"],
  ["goal_difference", "Goal Difference"],
  ["xg", "xG"],
  ["xga", "xGA"],
  ["possession", "Possession"],
  ["shots", "Shots"],
  ["shots_on_target", "Shots on Target"],
  ["form", "Form (last 5 matches)"],
];

function populateSeasons() {
  const currentYear = new Date().getFullYear();
  for (let year = currentYear; year >= 1992; year -= 1) {
    const option = document.createElement("option");
    option.value = String(year);
    option.textContent = String(year);
    seasonSelect.append(option);
  }
}

function setStatus(message, isError = false) {
  statusText.textContent = message;
  statusText.classList.toggle("error", isError);
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }
  return String(value);
}

function renderStats(data) {
  statsTable.innerHTML = "";
  fields.forEach(([key, label]) => {
    const row = document.createElement("tr");
    const labelCell = document.createElement("td");
    const valueCell = document.createElement("td");
    labelCell.textContent = label;
    valueCell.textContent = formatValue(data[key]);
    row.append(labelCell, valueCell);
    statsTable.append(row);
  });
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Request failed. Please try again.");
  }
  return payload;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const team = teamInput.value.trim();
  const season = seasonSelect.value;

  if (!team) {
    setStatus("Enter a team name.", true);
    return;
  }

  currentQuery = { team, season };
  downloadButton.disabled = true;
  analyzeButton.disabled = true;
  setStatus("Analyzing FBref data...");

  try {
    const params = new URLSearchParams({ name: team, season });
    const data = await fetchJson(`${API_BASE_URL}/team?${params.toString()}`);
    renderStats(data);
    downloadButton.disabled = false;
    setStatus("Analysis ready.");
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    analyzeButton.disabled = false;
  }
});

downloadButton.addEventListener("click", () => {
  if (!currentQuery) {
    return;
  }
  const params = new URLSearchParams({
    name: currentQuery.team,
    season: currentQuery.season,
  });
  window.location.href = `${API_BASE_URL}/team/csv?${params.toString()}`;
});

populateSeasons();
