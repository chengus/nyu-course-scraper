from typing import List, Optional, Dict, Any
import requests
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from fastapi import FastAPI, HTTPException, Query, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

import backend.scraper as scraper
import backend.sql as sql


def parse_meeting_html(meeting_html: str) -> tuple[str, str, str]:
    """
    Parse meeting_html to extract meeting pattern, start date, and end date.
    
    Example input:
    <div class="meet">TR 9:30am-10:45am<span class="meet-dates"> (1/20 to 5/5)</span></div>
    
    Returns:
    (meet_pattern, start_date, end_date)
    Example: ("TR 9:30am-10:45am", "1/20", "5/5")
    """
    if not meeting_html:
        return "", "", ""
    
    # Extract meeting pattern (text before <span> tag)
    pattern_match = re.search(r'<div[^>]*class="meet"[^>]*>([^<]+)', meeting_html)
    meet_pattern = pattern_match.group(1).strip() if pattern_match else ""
    
    # Extract dates from (START to END) format
    dates_match = re.search(r'\((\d+/\d+)\s+to\s+(\d+/\d+)\)', meeting_html)
    if dates_match:
        start_date = dates_match.group(1).strip()
        end_date = dates_match.group(2).strip()
    else:
        start_date = ""
        end_date = ""
    
    return meet_pattern, start_date, end_date

app = FastAPI(title="NYU Course Search API")

# Allow the React dev server (and other local origins) to call this API during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Check if frontend build exists (for production) and mount static files
frontend_build = (Path(__file__).resolve().parent / "../frontend/build").resolve()
if frontend_build.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_build / "static")), name="static")

@app.get("/")
async def root():
    """API root - returns basic information about the API or serves frontend"""
    if frontend_build.exists():
        return FileResponse(str(frontend_build / "index.html"))
    return {
        "name": "NYU Course Search API",
        "version": "1.0",
        "endpoints": {
            "search": "/search",
            "course_details": "/course-details",
            "database_status": "/database-status",
            "update_database": "/update-database"
        }
    }



def get_db():
    conn = sql.get_conn()
    try:
        yield conn
    finally:
        conn.close()


class SectionResult(BaseModel):
    section_id: int
    course_code: str
    course_title: str

    key: str | None
    code: str | None
    title: str | None
    hide: str | None
    crn: str | None
    no: str | None
    total: int | None
    schd: str | None
    stat: str | None
    isCancelled: str | None
    meets: str | None
    mpkey: str | None
    meetingTimes: str | None
    instr: str | None
    start_date: str | None
    end_date: str | None
    srcdb: str | None
    campus_group: str | None


class UpdateRequest(BaseModel):
    srcdb: str = "1264"
    career: str = "UGRD"
    camps: List[str] = ["WS@BRKLN,WS@INDUS", "AD@GLOBAL-WS,AD@WS,SH@GLOBAL-WS,WS*,WS@2BRD,WS@JD,WS@MT,WS@OC,WS@PU,WS@WS,WS@WW"]
    
    class Config:
        schema_extra = {
            "example": {
                "srcdb": "1264",
                "career": "UGRD",
                "camps": ["WS@BRKLN,WS@INDUS", "AD@GLOBAL-WS,AD@WS,SH@GLOBAL-WS,WS*,WS@2BRD,WS@JD,WS@MT,WS@OC,WS@PU,WS@WS,WS@WW"]
            }
        }


class UpdateResponse(BaseModel):
    status: str
    message: str
    files_downloaded: List[str]
    records_processed: int


class CourseDetailsRequest(BaseModel):
    group: str
    key: str
    srcdb: str
    matched: str
    
    class Config:
        schema_extra = {
            "example": {
                "group": "code:BIOL-UA 123",
                "key": "crn:8807",
                "srcdb": "1264",
                "matched": "crn:8807,8808,8809,8810,8811,8812,8813,8814,8815,8816,8817,8818,8819,8820,8821,8822,8823,8824,8825,8826"
            }
        }


@app.post("/course-details")
async def get_course_details(request: CourseDetailsRequest = Body(...)):
    """
    Get detailed information for a specific course from NYU's API.
    Caches results in the database to avoid repeated API calls.
    
    Parameters:
    - group: Course code identifier (e.g., "code:BIOL-UA 123")
    - key: CRN key (e.g., "crn:8807")
    - srcdb: Term code (e.g., "1264")
    - matched: Comma-separated list of matched CRNs
    """
    conn = None
    try:
        # Get database connection
        conn = sql.get_conn()
        sql.init_schema(conn)  # Ensure schema exists
        
        results = conn.execute(
            """SELECT description, clssnotes, hours_html, status, component,
                      instructional_method, campus_location, registration_restrictions,
                      meeting_html, meet_pattern, meet_start_date, meet_end_date,
                      dates_html, all_sections, details_json
               FROM course_details_cache 
               WHERE group_key = ? AND crn_key = ? AND srcdb = ?""",
            [request.group, request.key, request.srcdb]
        )
        cached = results.fetchone()
        
        if cached:
            # Return cached data with parsed fields
            return {
                "description": cached[0],
                "clssnotes": cached[1],
                "hours_html": cached[2],
                "status": cached[3],
                "component": cached[4],
                "instructional_method": cached[5],
                "campus_location": cached[6],
                "registration_restrictions": cached[7],
                "meeting_html": cached[8],
                "meet_pattern": cached[9],
                "meet_start_date": cached[10],
                "meet_end_date": cached[11],
                "dates_html": cached[12],
                "all_sections": json.loads(cached[13]) if cached[13] else [],
                "raw": json.loads(cached[14]) if cached[14] else {}
            }
        
        # Not in cache, fetch from API
        url = "https://bulletins.nyu.edu/class-search/api/"
        params = {
            "page": "fose",
            "route": "details"
        }
        
        payload = {
            "group": request.group,
            "key": request.key,
            "srcdb": request.srcdb,
            "matched": request.matched
        }
        
        headers = {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/json",
            "Origin": "https://bulletins.nyu.edu",
            "Referer": "https://bulletins.nyu.edu/class-search/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        
        response = requests.post(url, params=params, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        
        # Parse fields from result
        description = result.get('description', '')
        clssnotes = result.get('clssnotes', '')
        hours_html = result.get('hours_html', '')
        status = result.get('status', '')
        component = result.get('component', '')
        instructional_method = result.get('instructional_method', '')
        campus_location = result.get('campus_location', '')
        registration_restrictions = result.get('registration_restrictions', '')
        meeting_html = result.get('meeting_html', '')
        dates_html = result.get('dates_html', '')
        all_sections = json.dumps(result.get('allInGroup', []))
        
        # Parse meeting information
        meet_pattern, meet_start_date, meet_end_date = parse_meeting_html(meeting_html)
        
        # Cache the result with parsed fields
        conn.execute(
            """INSERT OR REPLACE INTO course_details_cache 
               (group_key, crn_key, srcdb, description, clssnotes, hours_html, status,
                component, instructional_method, campus_location, registration_restrictions,
                meeting_html, meet_pattern, meet_start_date, meet_end_date,
                dates_html, all_sections, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [request.group, request.key, request.srcdb, description, clssnotes, hours_html,
             status, component, instructional_method, campus_location, registration_restrictions,
             meeting_html, meet_pattern, meet_start_date, meet_end_date,
             dates_html, all_sections, json.dumps(result)]
        )
        conn.commit()
        
        # Return parsed fields in consistent format
        return {
            "description": description,
            "clssnotes": clssnotes,
            "hours_html": hours_html,
            "status": status,
            "component": component,
            "instructional_method": instructional_method,
            "campus_location": campus_location,
            "registration_restrictions": registration_restrictions,
            "meeting_html": meeting_html,
            "meet_pattern": meet_pattern,
            "meet_start_date": meet_start_date,
            "meet_end_date": meet_end_date,
            "dates_html": dates_html,
            "all_sections": result.get('allInGroup', []),
            "raw": result
        }
        
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch course details: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing course details: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@app.post("/update-database", response_model=UpdateResponse)
async def update_database(request: UpdateRequest = None, force: bool = Query(False, description="Force update even if less than 1 day old")):
    """
    Scrape course data from NYU's API and update the database.
    Only updates if the database is more than 1 day old (unless force=True).
    When updating, deletes all existing data and repopulates with fresh data.
    
    Parameters:
    - srcdb: Term code (e.g., "1264" for Spring 2026)
    - career: Career type (e.g., "UGRD" for undergraduate)
    - camps: List of campus codes to scrape
    - force: Force update even if less than 1 day old (query param)
    """
    if request is None:
        request = UpdateRequest()

    # Ingest locally into SQLite only
    conn = sql.get_conn()
    try:
        sql.init_schema(conn)
        sql.optimize_for_bulk_load(conn)

        last_update = sql.get_last_update_time(conn)
        if last_update and not force:
            last_update_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            # SQLite datetime('now') is UTC; use utcnow for consistent comparison
            time_since_update = datetime.utcnow() - last_update_dt.replace(tzinfo=None)
            # Guard against negative drift if clocks differ
            hours_since = max(time_since_update.total_seconds() / 3600, 0)
            hours_left = max(24 - hours_since, 0)
            if time_since_update < timedelta(days=1):
                return UpdateResponse(
                    status="skipped",
                    message=f"Database was updated {hours_since:.1f} hours ago. Will update in {hours_left:.1f} hours.",
                    files_downloaded=[],
                    records_processed=0
                )

        print("Clearing all existing data...")
        sql.clear_all_data(conn)

        files_downloaded: List[str] = []
        total_records = 0

        def scrape_campus(camp: str) -> tuple[str, Path]:
            path = scraper.scrape_and_save(
                srcdb=request.srcdb,
                career=request.career,
                camp=camp
            )
            return camp, path

        scrape_results: List[tuple[str, Path]] = []
        with ThreadPoolExecutor(max_workers=min(4, max(1, len(request.camps)))) as pool:
            futures = {pool.submit(scrape_campus, camp): camp for camp in request.camps}
            for future in as_completed(futures):
                camp, file_path = future.result()
                files_downloaded.append(str(file_path))
                scrape_results.append((camp, file_path))

        try:
            conn.execute("BEGIN")
            for camp, file_path in scrape_results:
                campus_group = "BROOKLYN" if ("BRKLN" in camp or "INDUS" in camp) else "WSQ"
                courses_data, sections_data = sql.prepare_json_data(file_path, campus_group)
                sql.insert_prepared_data(conn, courses_data, sections_data, commit=False)
                total_records += len(sections_data)
            sql.set_last_update_time(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return UpdateResponse(
            status="success",
            message=f"Successfully updated database with {total_records} records from {len(files_downloaded)} campus groups",
            files_downloaded=files_downloaded,
            records_processed=total_records
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Database update failed: {str(e)}"
        )
    finally:
        conn.close()


class DatabaseStatus(BaseModel):
    total_courses: int
    total_sections: int
    campus_groups: dict


@app.get("/database-status", response_model=DatabaseStatus)
def get_database_status():
    """
    Get current database statistics.
    """
    try:
        for conn in get_db():
            # Count courses
            results = conn.execute("SELECT COUNT(*) FROM courses")
            total_courses = results.fetchone()[0]
            
            # Count sections
            results = conn.execute("SELECT COUNT(*) FROM sections")
            total_sections = results.fetchone()[0]
            
            # Count by campus group
            results = conn.execute("SELECT campus_group, COUNT(*) FROM sections GROUP BY campus_group")
            campus_groups = {row[0]: row[1] for row in results.fetchall()}
            
            return DatabaseStatus(
                total_courses=total_courses,
                total_sections=total_sections,
                campus_groups=campus_groups
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get database status: {str(e)}"
        )


@app.get("/search", response_model=list[SectionResult])
def search_sections(
    code: Optional[str] = Query(None, description="Course/section code, e.g. 'MATH-UA 325'"),
    title: Optional[str] = Query(None, description="Course/section title"),
    crn: Optional[str] = Query(None, description="CRN"),
    schd: Optional[str] = Query(None, description="Schedule type, e.g. 'LEC'"),
    campus_group: Optional[str] = Query(None, description="Campus group, e.g. 'WSQ' or 'BROOKLYN'"),
):
    # Enforce at least one filter
    if not any([code, title, crn, schd, campus_group]):
        raise HTTPException(
            status_code=400,
            detail="At least one of code, title, crn, schd, campus_group must be provided.",
        )

    # Build query
    base_query = """
        SELECT
          s.id AS section_id,
          s.course_code AS course_code,
          c.title AS course_title,

          s.key,
          s.code,
          s.title,
          s.hide,
          s.crn,
          s.no,
          s.total,
          s.schd,
          s.stat,
          s.isCancelled,
          s.meets,
          s.mpkey,
          s.meetingTimes,
          s.instr,
          s.start_date,
          s.end_date,
          s.srcdb,
          s.campus_group
        FROM sections s
        LEFT JOIN courses c ON s.course_code = c.code
        WHERE 1=1
    """

    conditions = []
    params = []

    # Simple matching behavior:
    # - code/title: partial match (LIKE)
    # - crn/schd/campus_group: exact match
    if code:
        conditions.append("AND s.code LIKE ?")
        params.append(f"%{code}%")
    if title:
        # Search either section.title or course.title
        conditions.append("AND (s.title LIKE ? OR c.title LIKE ?)")
        params.extend([f"%{title}%", f"%{title}%"])
    if crn:
        conditions.append("AND s.crn = ?")
        params.append(crn)
    if schd:
        conditions.append("AND s.schd = ?")
        params.append(schd)
    if campus_group:
        conditions.append("AND s.campus_group = ?")
        params.append(campus_group)

    sql = base_query + "\n".join(conditions) + "\nORDER BY s.course_code, s.no"

    results: List[SectionResult] = []
    for conn in get_db():
        result_set = conn.execute(sql, params)
        rows = result_set.fetchall()
        for row in rows:
            # Convert row tuple to dict manually
            results.append(SectionResult(
                section_id=row[0],
                course_code=row[1],
                course_title=row[2],
                key=row[3],
                code=row[4],
                title=row[5],
                hide=row[6],
                crn=row[7],
                no=row[8],
                total=row[9],
                schd=row[10],
                stat=row[11],
                isCancelled=row[12],
                meets=row[13],
                mpkey=row[14],
                meetingTimes=row[15],
                instr=row[16],
                start_date=row[17],
                end_date=row[18],
                srcdb=row[19],
                campus_group=row[20]
            ))
        break  # exit generator loop after one use

    return results

# Catch-all route for React client-side routing (must be defined last)
if frontend_build.exists():
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React app for all unmatched routes (client-side routing)"""
        return FileResponse(str(frontend_build / "index.html"))

if __name__ == "__main__":
    # Run with: python backend.py (for quick local testing)
    # Or use: fastapi run backend/backend.py (FastAPI CLI with auto-reload from project root)
    # Or use: uvicorn backend.backend:app --reload --port 8000 (from project root)
    try:
        import uvicorn

        uvicorn.run("backend:app", host="127.0.0.1", port=8000, reload=True)
    except Exception:
        # uvicorn not installed; fallback to direct import (FastAPI requires ASGI server)
        print("Start the API with: cd backend && python backend.py")
        print("Or from project root: uvicorn backend.backend:app --reload --port 8000")
