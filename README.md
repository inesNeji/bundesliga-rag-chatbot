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
