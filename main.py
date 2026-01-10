import requests
import re
import logging
import sys
from functools import lru_cache
from typing import Dict

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/debug.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(
    {"User-Agent": "Bundesliga-RAG-Chatbot/1.0 (Educational Project)"}
)

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# ============================================================
# WIKIDATA QUERY
# ============================================================

def query_wikidata(sparql_query: str) -> list:
    try:
        logger.info("[SPARQL] Sending query")
        response = SESSION.get(
            WIKIDATA_ENDPOINT,
            params={"query": sparql_query, "format": "json"},
            timeout=10,
        )
        response.raise_for_status()

        data = response.json()
        rows = data["results"]["bindings"]
        logger.info(f"[SPARQL] Returned {len(rows)} rows")
        return rows

    except Exception as exc:
        logger.error(f"[SPARQL] Failed: {exc}")
        return []

# ============================================================
# CLUB DATA
# ============================================================

@lru_cache(maxsize=1)
def get_current_bundesliga_clubs() -> Dict[str, Dict[str, str]]:
    query = """
    SELECT ?team ?teamLabel ?cityLabel WHERE {
      ?team wdt:P31 wd:Q476028 ;
            wdt:P118 wd:Q82595 ;
            wdt:P159 ?city .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    """

    results = query_wikidata(query)
    mapping: Dict[str, Dict[str, str]] = {}

    for row in results:
        club = row["teamLabel"]["value"]
        qid = row["team"]["value"].split("/")[-1]
        city = row["cityLabel"]["value"].lower()

        club_info = {"name": club, "qid": qid}

        mapping[city] = club_info

        if "pauli" in club.lower():
            mapping["pauli"] = club_info
            mapping["st. pauli"] = club_info

        elif "hamburg" in club.lower():
            mapping["hamburg"] = club_info

    logger.info(f"Loaded {len(mapping)} city aliases for Bundesliga clubs")
    return mapping

# ============================================================
# ENTITY EXTRACTION
# ============================================================

KNOWN_ENTITIES = {
    "berlin","hamburg","munich","münchen","cologne","köln",
    "dortmund","frankfurt","leipzig","bremen","stuttgart",
    "mainz","freiburg","wolfsburg","leverkusen","heidenheim",
    "pauli","st. pauli, Konstanz, constance, fc st. pauli, fc st pauli,lindau, lindau im bodensee, bodensee, fc lindau, fc lindau 04, fc lindau 04 e.v.",
}

def extract_city_or_club(user_query: str) -> str | None:
    """
    Try to extract a known city or club keyword from the user query.
    Returns None if nothing is recognized.
    """
    query_lower = user_query.lower()

    words = re.findall(r"\b[a-zäöüß\.]+\b", query_lower)

    for word in words:
        if word in KNOWN_ENTITIES:
            logger.info(f"Recognized entity: {word}")
            return word

    logger.info("No recognizable Bundesliga entity found")
    return None


# ============================================================
# COACH + WIKIPEDIA
# ============================================================

def get_current_coach(club_qid: str):
    query = f"""
    SELECT ?coach ?coachLabel ?article WHERE {{
      wd:{club_qid} p:P286 ?statement .
      ?statement ps:P286 ?coach .
      FILTER NOT EXISTS {{ ?statement pq:P582 ?end }}
      OPTIONAL {{
        ?article schema:about ?coach ;
                 schema:isPartOf <https://en.wikipedia.org/> .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }} LIMIT 1
    """

    rows = query_wikidata(query)

    if not rows:
        return None, "No current coach found."

    coach = rows[0]["coachLabel"]["value"]
    article = rows[0].get("article", {}).get("value")

    logger.info(f"[COACH] {coach}")

    if not article:
        return coach, "No Wikipedia article available."

    title = article.split("/")[-1]

    try:
        response = SESSION.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "format": "json",
            },
            timeout=10,
        )
        response.raise_for_status()

        pages = response.json()["query"]["pages"]
        text = next(iter(pages.values())).get("extract", "")

        text = text[:600]   # hard cap to avoid giant prompts
        logger.info(f"[WIKI] {len(text)} chars")

        return coach, text or "No summary available."

    except Exception as exc:
        logger.error(f"[WIKI] Failed: {exc}")
        return coach, "Wikipedia fetch failed."

# ============================================================
# PROMPT
# ============================================================

def build_llm_prompt(user, club, coach, info):
    return (
        "You are a helpful assistant specialized in German Bundesliga football.\n\n"
        f"Context:\nClub: {club}\nCoach: {coach}\nAbout: {info}\n\n"
        f"User question: {user}\nAnswer:"
    )

# ============================================================
# PIPELINE
# ============================================================

def handle_user_query(user_query: str) -> str:
    """
    Process a user query to extract a Bundesliga club, retrieve its current coach,
    and build a RAG-style LLM prompt. Handles unknown clubs gracefully.
    """
    try:
        # Try to extract a known city or club from the query
        entity = extract_city_or_club(user_query)

        # If no recognizable entity found, return polite fallback
        if not entity:
            return build_llm_prompt(
                user_query,
                "Unknown",
                "Unknown",
                "I'm sorry, we don't know who you mean."
            )

        # Load current Bundesliga clubs
        clubs = get_current_bundesliga_clubs()

        # If entity not in our mapping, return polite fallback
        if entity not in clubs:
            return build_llm_prompt(
                user_query,
                "Unknown",
                "Unknown",
                "I'm sorry, we don't know who you mean."
            )

        # Retrieve club info and current coach
        club = clubs[entity]
        coach_name, coach_info = get_current_coach(club["qid"])

        # Build final LLM prompt
        return build_llm_prompt(
            user_query,
            club["name"],
            coach_name or "Unknown",
            coach_info
        )

    except Exception:
        logger.exception("[PIPELINE FAILED]")
        return build_llm_prompt(
            user_query,
            "Error",
            "Error",
            "Internal error occurred while processing your query."
        )

# ============================================================
# CLI
# ============================================================

def run_chat_console():
    print("⚽ Bundesliga Coach RAG\nType 'exit' to quit")

    while True:
        q = input("\n> ").strip()
        if q.lower() in {"exit","quit"}:
            break

        prompt = handle_user_query(q)
        print("\n--- Generated Prompt ---\n")
        print(prompt)
        print("\n" + "-"*50)

if __name__ == "__main__":
    run_chat_console()
