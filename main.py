import requests
import re
import logging
import sys
from functools import lru_cache
from typing import Dict, Tuple, Optional

# ============================================================
# LOGGING SETUP
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/debug.log"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger(__name__)

# ============================================================
# HTTP SESSION (reuse connection for performance)
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(
    {"User-Agent": "Bundesliga-RAG-Chatbot/1.0 (Educational Project)"}
)

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# ============================================================
# WIKIDATA HELPERS
# ============================================================

def query_wikidata(sparql_query: str) -> list:
    """
    Execute a SPARQL query against Wikidata and return bindings.

    Args:
        sparql_query (str): SPARQL query string

    Returns:
        list: SPARQL result bindings (empty list on failure)
    """
    try:
        response = SESSION.get(
            WIKIDATA_ENDPOINT,
            params={"query": sparql_query, "format": "json"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info("SPARQL query successful")
        return response.json()["results"]["bindings"]

    except requests.RequestException as exc:
        logger.error(f"Wikidata query failed: {exc}")
        return []

# ============================================================
# BUNDESLIGA DATA
# ============================================================

@lru_cache(maxsize=1)
def get_current_bundesliga_clubs() -> Dict[str, Dict[str, str]]:
    """
    Fetch all current Bundesliga clubs and map them to city keywords.

    Returns:
        dict: {city_key -> {name, qid}}
    """
    query = """
    SELECT ?team ?teamLabel ?cityLabel WHERE {
      ?team wdt:P31 wd:Q476028 ;   # instance of football club
            wdt:P118 wd:Q82595 ;   # league: Bundesliga
            wdt:P159 ?city .
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }
    """

    results = query_wikidata(query)
    mapping: Dict[str, Dict[str, str]] = {}

    for row in results:
        club_name = row["teamLabel"]["value"]
        club_qid = row["team"]["value"].split("/")[-1]
        city = row.get("cityLabel", {}).get("value", "").lower()

        club_info = {"name": club_name, "qid": club_qid}

        if city:
            mapping[city] = club_info

        # Special handling for common aliases
        if "pauli" in club_name.lower():
            mapping["pauli"] = club_info
            mapping["st. pauli"] = club_info

        if "hamburg" in city or "hamburg" in club_name.lower():
            mapping["hamburg"] = club_info

    logger.info(f"Loaded {len(mapping)} city aliases for Bundesliga clubs")
    return mapping

# ============================================================
# ENTITY EXTRACTION
# ============================================================

def extract_city_or_club(user_query: str) -> str:
    """
    Extract a known city or club keyword from the user query.

    Args:
        user_query (str): Raw user input

    Returns:
        str: extracted keyword

    Raises:
        ValueError: if no entity could be identified
    """
    query = user_query.lower()

    known_entities = {
        "berlin",
        "munich",
        "münchen",
        "heidenheim",
        "hamburg",
        "pauli",
        "st. pauli",
    }

    words = re.findall(r"\b[a-zäöüß\.]+\b", query)

    for word in words:
        if word in known_entities:
            logger.info(f"Recognized entity: {word}")
            return word

    raise ValueError("No Bundesliga city or club recognized")

# ============================================================
# COACH INFORMATION
# ============================================================

def get_current_coach(club_qid: str) -> Tuple[Optional[str], str]:
    """
    Retrieve the current head coach of a Bundesliga club.

    Args:
        club_qid (str): Wikidata Q-ID of the club

    Returns:
        tuple: (coach_name | None, coach_background_text)
    """
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

    results = query_wikidata(query)

    if not results:
        return None, "No current coach information found."

    coach_name = results[0]["coachLabel"]["value"]
    article_url = results[0].get("article", {}).get("value")

    if not article_url:
        return coach_name, "No background information available."

    title = article_url.split("/")[-1].replace("_", " ")

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
        extract = next(iter(pages.values())).get("extract", "")
        return coach_name, extract.strip() or "No intro text available."

    except requests.RequestException as exc:
        logger.error(f"Wikipedia request failed: {exc}")
        return coach_name, "Could not retrieve coach background."

# ============================================================
# PROMPT CONSTRUCTION (RAG OUTPUT)
# ============================================================

def build_llm_prompt(
    user_query: str, club: str, coach: str, coach_info: str
) -> str:
    """
    Build the final prompt for the LLM.

    Returns:
        str: Prompt text
    """
    system_prompt = (
        "You are a helpful assistant specialized in German 1. Bundesliga football. "
        "Answer concisely and factually using only the provided context."
    )

    context = (
        f"Club: {club}\n"
        f"Current coach: {coach}\n"
        f"About the coach: {coach_info}"
    )

    return (
        f"{system_prompt}\n\n"
        f"Context:\n{context}\n\n"
        f"User question: {user_query}\n"
        f"Answer:"
    )

# ============================================================
# MAIN PROCESSING PIPELINE
# ============================================================

def handle_user_query(user_query: str) -> str:
    """
    Full pipeline:
    - extract entity
    - map to club
    - fetch coach info
    - build LLM prompt
    """
    try:
        entity = extract_city_or_club(user_query)
        clubs = get_current_bundesliga_clubs()

        if entity not in clubs:
            return build_llm_prompt(
                user_query,
                "Unknown",
                "Unknown",
                f"No current Bundesliga club found for '{entity}'.",
            )

        club = clubs[entity]
        coach_name, coach_info = get_current_coach(club["qid"])

        return build_llm_prompt(
            user_query,
            club["name"],
            coach_name or "Unknown",
            coach_info,
        )

    except Exception:
        logger.exception("Unexpected processing error")
        return build_llm_prompt(
            user_query,
            "Error",
            "Error",
            "An internal error occurred while retrieving data.",
        )

# ============================================================
# CHAT CONSOLE (CLI)
# ============================================================

def run_chat_console() -> None:
    """
    Interactive command-line chat interface.
    """
    print("=" * 60)
    print("⚽ Bundesliga Coach RAG Chatbot")
    print("Ask questions like:")
    print("  - Who is the coach of Hamburg?")
    print("  - Tell me about the coach in Munich")
    print("Type 'exit' or 'quit' to leave.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n> ").strip()
            if user_input.lower() in {"exit", "quit"}:
                print("\nGoodbye 👋")
                break

            if not user_input:
                continue

            prompt = handle_user_query(user_input)
            print("\n--- Generated LLM Prompt ---\n")
            print(prompt)
            print("\n" + "-" * 60)

        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye 👋")
            break

# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_chat_console()
