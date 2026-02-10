(short) nyu-course-scraper

![NYU Bobcat Search logo](frontend/logo.png)

NYU Bobcat Search is a full-stack app that scrapes NYU course data and lets you search, filter, and inspect course offerings through a simple web UI backed by a FastAPI service.

Features
--------

- Search courses by code, title, CRN, schedule type, and campus group.
- Scrape and refresh the course database from NYU's API.
- View detailed course metadata like descriptions, prerequisites, and units.
- Check database status and campus breakdowns for quick sanity checks.

Development startup
---------------

### Docker
`docker-compose up --build`

### Backend (FastAPI)

```bash
cd backend
uv run fastapi run backend.py
```

### Frontend (React)

```bash
cd frontend
npm install
npm start
```

Notes
-----

- The frontend expects the backend at http://127.0.0.1:8000 (see `frontend/src/api.js`).
- CORS is enabled for `http://localhost:3000` and `http://127.0.0.1:3000` while developing.
- The backend stores course data in `nyu_courses.db`. Ensure it exists and is populated before searching.

API Endpoints
-------------

### Search Courses
`GET /search`

Search for courses with optional filters:
- `code`: Course code (e.g., "MATH-UA 325")
- `title`: Course title (partial match)
- `crn`: CRN number
- `schd`: Schedule type (e.g., "LEC")
- `campus_group`: Campus group (e.g., "WSQ" or "BROOKLYN")

Example: `http://127.0.0.1:8000/search?code=MATH&campus_group=WSQ`

### Update Database
`POST /update-database`

Scrape course data from NYU's API and update the database.

Request body (all optional):
```json
{
  "srcdb": "1264",
  "career": "UGRD",
  "camps": ["WS@BRKLN,WS@INDUS", "AD@GLOBAL-WS,AD@WS,SH@GLOBAL-WS,WS*"]
}
```

Or use the simple version with defaults:
`POST /update-database-simple`

**Note:** The update process now clears existing data for the same term (srcdb) and campus group before inserting new data to prevent duplicates.

### Course Details
`POST /course-details`

Get detailed information for a specific course from NYU's API. Results are parsed and cached in the database with individual columns for easy access.

Parsed fields include:
- `description`: Course description
- `notes`: Additional notes
- `prereqs`: Prerequisites
- `coreqs`: Corequisites
- `min_units`, `max_units`: Credit units
- `grading`: Grading method
- `campus`, `location`: Location information

Request body:
```json
{
  "group": "code:BIOL-UA 123",
  "key": "crn:8807",
  "srcdb": "1264",
  "matched": "crn:8807,8808,8809"
}
```

Returns detailed course information including descriptions, prerequisites, and section details.

### Database Status
`GET /database-status`

Get current database statistics including total courses, sections, and breakdown by campus.

Example response:
```json
{
  "total_courses": 1234,
  "total_sections": 5678,
  "campus_groups": {
    "WSQ": 4000,
    "BROOKLYN": 1678
  }
}
```

