import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

WSQ_FILE = "wsq.json"
BROOKLYN_FILE = "brooklyn.json"
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOCAL_DB = DATA_DIR / "nyu-courses.db"  # Local SQLite database file


def get_conn():
    """Get a local SQLite connection (no remote sync)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(LOCAL_DB))


def init_schema(conn) -> None:
    # Courses table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS courses (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      code           TEXT NOT NULL UNIQUE,
      subject        TEXT,
      catalog_number TEXT,
      title          TEXT NOT NULL
    );
    """)

    # Sections table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS sections (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,

      course_code    TEXT NOT NULL,

      key            TEXT,
      code           TEXT,
      title          TEXT,
      hide           TEXT,
      crn            TEXT,
      no             TEXT,
      total          INTEGER,
      schd           TEXT,
      stat           TEXT,
      isCancelled    TEXT,
      meets          TEXT,
      mpkey          TEXT,
      meetingTimes   TEXT,
      instr          TEXT,
      start_date     TEXT,
      end_date       TEXT,
      srcdb          TEXT,

      campus_group   TEXT,

      FOREIGN KEY (course_code) REFERENCES courses(code)
    );
    """)

    # Course details cache table
    conn.execute("""
    CREATE TABLE IF NOT EXISTS course_details_cache (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      group_key      TEXT NOT NULL,
      crn_key        TEXT NOT NULL,
      srcdb          TEXT NOT NULL,
      
      description    TEXT,
      clssnotes      TEXT,
      hours_html     TEXT,
      status         TEXT,
      component      TEXT,
      instructional_method TEXT,
      campus_location TEXT,
      registration_restrictions TEXT,
      meeting_html   TEXT,
      meet_pattern   TEXT,
      meet_start_date TEXT,
      meet_end_date  TEXT,
      dates_html     TEXT,
      all_sections   TEXT,
      
      details_json   TEXT NOT NULL,
      cached_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      
      UNIQUE(group_key, crn_key, srcdb)
    );
    """)
    
    # Metadata table for tracking last update time
    conn.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
      key            TEXT PRIMARY KEY,
      value          TEXT,
      updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Note: Schema is managed locally; no migrations needed for this demo
    conn.commit()


def optimize_for_bulk_load(conn) -> None:
    """Speed up large inserts on the local SQLite database."""
    # These pragmas trade durability for throughput during bulk writes.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")


def get_last_update_time(conn) -> Optional[str]:
    """Get the last update timestamp from metadata table"""
    result = conn.execute(
        "SELECT value FROM metadata WHERE key = 'last_update'"
    ).fetchone()
    return result[0] if result else None


def set_last_update_time(conn) -> None:
    """Set the last update timestamp to current time"""
    conn.execute(
        """INSERT OR REPLACE INTO metadata (key, value, updated_at) 
           VALUES ('last_update', datetime('now'), datetime('now'))"""
    )
    conn.commit()


def clear_all_data(conn) -> None:
    """Delete all courses and sections data for a fresh update"""
    conn.execute("DELETE FROM sections")
    conn.execute("DELETE FROM courses")
    conn.execute("DELETE FROM course_details_cache")
    conn.commit()


def split_code(code: str) -> Tuple[Optional[str], Optional[str]]:
    """
    'MATH-UA 325' -> ('MATH-UA', '325')
    'ACA-UF 101'  -> ('ACA-UF', '101')
    Fallback: (None, None) if format is unexpected.
    """
    if not code:
        return None, None
    parts = code.rsplit(" ", 1)
    if len(parts) == 2:
        subject, catalog = parts
        return subject.strip(), catalog.strip()
    return None, None


def upsert_course(conn, code: str, title: str) -> None:
    """
    Insert a course into courses if it doesn't exist.
    """
    subject, catalog = split_code(code)
    conn.execute("""
        INSERT OR IGNORE INTO courses (code, subject, catalog_number, title)
        VALUES (?, ?, ?, ?)
    """, [code, subject, catalog, title])


def to_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def insert_section(
    conn,
    record: Dict[str, Any],
    campus_group: str
) -> None:
    """
    Insert a single section row corresponding to one JSON record.
    """
    code = record.get("code", "")

    conn.execute("""
        INSERT INTO sections (
          course_code,
          key,
          code,
          title,
          hide,
          crn,
          no,
          total,
          schd,
          stat,
          isCancelled,
          meets,
          mpkey,
          meetingTimes,
          instr,
          start_date,
          end_date,
          srcdb,
          campus_group
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        code,                              # course_code FK
        record.get("key"),
        record.get("code"),
        record.get("title"),
        record.get("hide"),
        record.get("crn"),
        record.get("no"),
        to_int_or_none(record.get("total")),
        record.get("schd"),
        record.get("stat"),
        record.get("isCancelled"),
        record.get("meets"),
        record.get("mpkey"),
        record.get("meetingTimes"),
        record.get("instr"),
        record.get("start_date"),
        record.get("end_date"),
        record.get("srcdb"),
        campus_group,
    ])


def prepare_json_data(
    json_path: Path,
    campus_group: str
) -> Tuple[List[Tuple], List[List]]:
    """
    Load a JSON file and prepare course and section data for insertion.
    Returns (courses_data, sections_data) without modifying the database.
    """
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    results: List[Dict[str, Any]] = data.get("results", [])
    print(f"Processing {json_path} ({campus_group}) with {len(results)} records", flush=True)

    # Prepare bulk data
    courses_data = []
    sections_data = []
    
    for i, record in enumerate(results):
        # Progress indicator every 1000 records
        if i > 0 and i % 1000 == 0:
            print(f"  Prepared {i}/{len(results)} records...", flush=True)
        
        code = record.get("code", "")
        title = record.get("title", "")
        if not code or not title:
            continue

        # Prepare course data
        subject, catalog = split_code(code)
        courses_data.append((code, subject, catalog, title))
        
        # Prepare section data
        sections_data.append([
            code,  # course_code FK
            record.get("key"),
            record.get("code"),
            record.get("title"),
            record.get("hide"),
            record.get("crn"),
            record.get("no"),
            to_int_or_none(record.get("total")),
            record.get("schd"),
            record.get("stat"),
            record.get("isCancelled"),
            record.get("meets"),
            record.get("mpkey"),
            record.get("meetingTimes"),
            record.get("instr"),
            record.get("start_date"),
            record.get("end_date"),
            record.get("srcdb"),
            campus_group,
        ])
    
    print(f"  Data preparation complete. Prepared {len(courses_data)} courses and {len(sections_data)} sections", flush=True)
    return courses_data, sections_data


def insert_prepared_data(
    conn,
    courses_data: List[Tuple],
    sections_data: List[List],
    *,
    commit: bool = True,
) -> None:
    """
    Insert prepared course and section data into the database.
    This should be called from the API endpoint that manages database updates.
    """
    # Bulk insert courses (ignore duplicates)
    print(f"  Inserting {len(courses_data)} courses...", flush=True)
    conn.executemany("""
        INSERT OR IGNORE INTO courses (code, subject, catalog_number, title)
        VALUES (?, ?, ?, ?)
    """, courses_data)

    # Bulk insert sections
    print(f"  Inserting {len(sections_data)} sections...", flush=True)
    conn.executemany("""
        INSERT INTO sections (
          course_code, key, code, title, hide, crn, no, total,
          schd, stat, isCancelled, meets, mpkey, meetingTimes,
          instr, start_date, end_date, srcdb, campus_group
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sections_data)
    
    if commit:
        conn.commit()
    print(f"  Database insert complete")


def main() -> None:
    conn = get_conn()
    init_schema(conn)

    base_dir = DATA_DIR

    wsq_path = base_dir / WSQ_FILE
    brooklyn_path = base_dir / BROOKLYN_FILE

    all_courses = []
    all_sections = []
    
    if wsq_path.exists():
        courses, sections = prepare_json_data(wsq_path, campus_group="WSQ")
        all_courses.extend(courses)
        all_sections.extend(sections)
    else:
        print(f"Skipping {wsq_path}, file not found.")

    if brooklyn_path.exists():
        courses, sections = prepare_json_data(brooklyn_path, campus_group="BROOKLYN")
        all_courses.extend(courses)
        all_sections.extend(sections)
    else:
        print(f"Skipping {brooklyn_path}, file not found.")
    
    # Insert all prepared data
    if all_courses or all_sections:
        insert_prepared_data(conn, all_courses, all_sections)

    conn.close()
    print("All done. Database updated.")


if __name__ == "__main__":
    main()
