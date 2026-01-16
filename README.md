# bundesliga-rag-chatbot
# Bundesliga Coach RAG Chatbot

Python script for a hypothetical RAG chatbot that answers questions about current coaches of 1. Bundesliga clubs using **Wikidata** (SPARQL) and **Wikipedia**.

Built for the **Pantopix Coding Challenge**.

## Features
- Extracts city / club key from colloquial user questions (case-insensitive, handles possessives like "heidenheims")
- Fetches current Bundesliga season, participating clubs and their cities from Wikidata
- Retrieves current head coach via SPARQL (only coaches without end date)
- Gets short coach biography from Wikipedia article intro
- Builds a ready-to-use LLM prompt with system instructions + context + user question
- Full logging to console + `logs/debug.log` for debugging hallucinations / wrong answers
- Graceful error handling with user-friendly fallbacks

Special handling:
- "pauli" or "Pauli" → FC St. Pauli
- Hamburg clubs (if both present)

## How to Run

1. Clone the repository:
   ```bash
   git clone https://github.com/inesNeji/bundesliga-rag-chatbot.git
   cd bundesliga-rag-chatbot
## Answers to Additional Questions (Pantopix Challenge)

1. **Advantages and disadvantages of using additional information for a chatbot instead of letting the LLM answer without it**  
   **Advantages**: Reduces hallucinations significantly, ensures factual & up-to-date answers (especially for changing data like coaches), makes responses verifiable and grounded in sources.  
   **Disadvantages**: Adds latency (API calls), introduces dependency on external services (Wikidata/Wikipedia downtime or rate limits), more complex implementation & error handling.

2. **Advantages and disadvantages of querying for this data on every user question**  
   **Advantages**: Guarantees the freshest possible data (coaches can change mid-season), no need to manage cache invalidation or staleness.  
   **Disadvantages**: Increases response time (1–3 seconds per query), higher network/API usage, potential rate-limit issues during heavy use.

3. **How would the process change if the information about coaches only were available via PDF?**  
   Real-time SPARQL queries would be replaced by periodic PDF downloads + parsing (e.g. using PyPDF2 or pdfplumber). Data would need scheduled updates (cron job/manual), becoming stale quickly. Runtime would be faster (local lookup), but maintenance effort much higher and error-prone (PDF layouts change often).

4. **Do you see potential for agents in this process? If so, where and how?**  
   Yes — agents (e.g. LangChain/LlamaIndex style) could:  
   - Clarify ambiguous queries ("Hamburg" → HSV or St. Pauli?) via follow-up questions  
   - Cross-verify Wikidata with recent news/web search if data seems outdated  
   - Chain multiple retrieval steps (club → coach → career stats)  
   - Handle fallbacks gracefully when sources fail

5. **How do these kinds of processes profit from a data model that models the specific domain knowledge?**  
   A rich domain model (like Wikidata's ontology for football: clubs, seasons, coaches, properties) enables precise semantic queries, automatic disambiguation, inference of missing facts (e.g. city from stadium), easier integration of new sources, and structured context feeding to the LLM → better accuracy and less hallucination.