from typing import List, Optional

import sqlite3
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

DB_PATH = "nyu_courses.db"

app = FastAPI(title="NYU Course Search API")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        for row in rows:
            results.append(SectionResult(**dict(row)))
        break  # exit generator loop after one use

    return results
