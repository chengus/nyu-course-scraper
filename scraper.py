import json
from pathlib import Path
import requests


BASE_URL = "https://bulletins.nyu.edu/class-search/api/"

# These are based on your incognito request
DEFAULT_HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Origin": "https://bulletins.nyu.edu",
    "Referer": "https://bulletins.nyu.edu/class-search/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
    ),
    "X-Requested-With": "XMLHttpRequest",
    # sec-ch-ua headers are optional; server usually doesn’t require them
}


def build_payload(srcdb: str, career: str, camp: str) -> dict:
    """
    Build the JSON body corresponding to the URL-encoded payload you captured:

    Decoded payload:
    {
      "other": { "srcdb": "1264" },
      "criteria": [
        { "field": "career", "value": "UGRD" },
        { "field": "camp", "value": "WS@BRKLN,WS@INDUS" }
      ]
    }
    """
    return {
        "other": {
            "srcdb": srcdb,
        },
        "criteria": [
            {"field": "career", "value": career},
            {"field": "camp", "value": camp},
        ],
    }


def fetch_raw_data(srcdb: str, career: str, camp: str) -> dict:
    """
    Perform a single POST to the bulletin API for the given term/career/camp.
    No pagination handling yet — just one request, one JSON response.
    """
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # Query string parameters from your incognito request:
    # page=fose&route=search&career=UGRD&camp=WS%40BRKLN%2CWS%40INDUS
    params = {
        "page": "fose",
        "route": "search",
        "career": career,
        "camp": camp,  # requests will encode @ and , appropriately
    }

    payload = build_payload(srcdb=srcdb, career=career, camp=camp)

    resp = session.post(
        BASE_URL,
        params=params,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def slugify_camp(camp: str) -> str:
    """
    Turn something like 'WS@BRKLN,WS@INDUS' into 'WS-BRKLN_WS-INDUS'
    so it’s safe to use in filenames.
    """
    return (
        camp.replace("@", "-")
            .replace(",", "_")
            .replace("*", "STAR")
            .replace(" ", "")
    )


def save_json(data: dict, out_dir: str, srcdb: str, career: str, camp: str) -> Path:
    """
    Save the raw JSON to a file under out_dir.
    File name encodes srcdb, career, and camp.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    camp_slug = slugify_camp(camp)
    filename = f"classes_srcdb-{srcdb}_career-{career}_camp-{camp_slug}.json"
    full_path = out_path / filename

    with full_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return full_path


def scrape_and_save(srcdb: str, career: str, camp: str, out_dir: str = "data/raw") -> Path:
    """
    High-level helper: fetch raw JSON for given parameters and save to disk.
    Returns the path of the saved file.
    """
    data = fetch_raw_data(srcdb=srcdb, career=career, camp=camp)
    path = save_json(data, out_dir=out_dir, srcdb=srcdb, career=career, camp=camp)
    return path


if __name__ == "__main__":
    # Example usage: Spring 2026 (srcdb=1264), undergrad, Brooklyn + Industry
    SRCDB = "1264"       # term code
    CAREER = "UGRD"

    # Brooklyn / Industry City
    CAMP_BROOKLYN = "WS@BRKLN,WS@INDUS"

    # WSQ + related (from your first message) — you can tweak this string
    CAMP_WSQ = (
        "AD@GLOBAL-WS,AD@WS,SH@GLOBAL-WS,WS*,WS@2BRD,WS@JD,"
        "WS@MT,WS@OC,WS@PU,WS@WS,WS@WW,AD@GLOBAL-WS"
    )

    # Scrape Brooklyn
    brooklyn_path = scrape_and_save(SRCDB, CAREER, CAMP_BROOKLYN)
    print(f"Saved Brooklyn/Industry data to: {brooklyn_path}")

    # Scrape WSQ/global
    wsq_path = scrape_and_save(SRCDB, CAREER, CAMP_WSQ)
    print(f"Saved WSQ/global data to: {wsq_path}")
