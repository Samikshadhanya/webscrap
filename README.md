# Football Analytics CSV Generator

A production-ready MVP for generating CSV-ready football team analytics from FBref data.

## Stack

- Frontend: HTML, CSS, vanilla JavaScript
- Backend: Python FastAPI
- Data: FBref via `pandas.read_html`, with `requests` and BeautifulSoup available for future parsing needs
- Hosting: frontend can deploy to Vercel, backend can deploy to Render

## Project Structure

```text
frontend/
  index.html
  style.css
  script.js

backend/
  main.py
  requirements.txt
  render.yaml
  services/
    fbref_service.py
  models/
    team.py
  utils/
    csv_export.py
    rate_limit.py
```

## Run Locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Then open `frontend/index.html` in a browser.

For a deployed backend, set the frontend API URL before loading `script.js`:

```html
<script>
  window.FOOTBALL_API_URL = "https://your-render-service.onrender.com";
</script>
<script src="script.js"></script>
```

## API

```http
GET /team?name=Arsenal&season=2025
GET /team/csv?name=Arsenal&season=2025
GET /health
POST /admin/refresh-season?season=2025
POST /admin/refresh-season-now?season=2025
```

## Notes

- Results are cached in memory and on disk for 24 hours by default to reduce repeated scraping.
- A lightweight IP-based rate limiter protects the API from bursts.
- FBref requests are intentionally slowed and retried with backoff. This lowers block risk, but no hosted app can guarantee FBref will allow every live scrape.
- Missing FBref columns return sensible `N/A`, `0`, or `null` values.
- The service layer is intentionally isolated so player analysis, match analysis, team comparison, and scheduled updates can be added later.

## Production Scraping Settings

Set these on Render when needed:

```text
CACHE_TTL_SECONDS=86400
FBREF_MIN_REQUEST_INTERVAL_SECONDS=8
FBREF_MAX_RETRIES=3
CACHE_DIR=.cache/team-stats
```

For the most reliable hosted version, pre-warm cache with scheduled updates and let user clicks read cached data first.

## Recommended Hosting Flow

1. Deploy the backend on Render.
2. Deploy the frontend on Vercel.
3. Set `window.FOOTBALL_API_URL` in `frontend/index.html` to the Render URL.
4. Set `ADMIN_REFRESH_TOKEN` on Render.
5. Use Render Cron Jobs or an external scheduler to call:

```http
POST https://your-render-service.onrender.com/admin/refresh-season?season=2025
X-Admin-Token: your-secret-token
```

After the season refresh succeeds, normal user clicks should read cached team data and generate CSV downloads without scraping FBref again.
