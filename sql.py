import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DB_PATH = "nyu_courses.db"

WSQ_FILE = "wsq.json"
BROOKLYN_FILE = "brooklyn.json"


def get_conn(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # Courses table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS courses (
      id             INTEGER PRIMARY KEY AUTOINCREMENT,
      code           TEXT NOT NULL UNIQUE,
      subject        TEXT,
      catalog_number TEXT,
      title          TEXT NOT NULL
    );
    """)

    # Sections table
    cur.execute("""
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


def upsert_course(conn: sqlite3.Connection, code: str, title: str) -> None:
    """
    Insert a course into courses if it doesn't exist.
    """
    subject, catalog = split_code(code)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO courses (code, subject, catalog_number, title)
        VALUES (?, ?, ?, ?)
    """, (code, subject, catalog, title))


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
    conn: sqlite3.Connection,
    record: Dict[str, Any],
    campus_group: str
) -> None:
    """
    Insert a single section row corresponding to one JSON record.
    """
    cur = conn.cursor()

    code = record.get("code", "")

    cur.execute("""
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
    """, (
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
    ))


def process_json_file(
    conn: sqlite3.Connection,
    json_path: Path,
    campus_group: str
) -> None:
    """
    Load a JSON file (wsq.json or brooklyn.json) and populate courses+sections.
    """
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    results: List[Dict[str, Any]] = data.get("results", [])
    print(f"Processing {json_path} ({campus_group}) with {len(results)} records")

    cur = conn.cursor()
    for record in results:
        code = record.get("code", "")
        title = record.get("title", "")
        if not code or not title:
            continue

        # Ensure course exists
        upsert_course(conn, code, title)

        # Insert section
        insert_section(conn, record, campus_group)

    conn.commit()
    print(f"Done {json_path}")


def main() -> None:
    conn = get_conn(DB_PATH)
    init_schema(conn)

    base_dir = Path("data")

    wsq_path = base_dir / WSQ_FILE
    brooklyn_path = base_dir / BROOKLYN_FILE

    if wsq_path.exists():
        process_json_file(conn, wsq_path, campus_group="WSQ")
    else:
        print(f"Skipping {wsq_path}, file not found.")

    if brooklyn_path.exists():
        process_json_file(conn, brooklyn_path, campus_group="BROOKLYN")
    else:
        print(f"Skipping {brooklyn_path}, file not found.")

    conn.close()
    print(f"All done. Database written to {DB_PATH}")


if __name__ == "__main__":
    main()
