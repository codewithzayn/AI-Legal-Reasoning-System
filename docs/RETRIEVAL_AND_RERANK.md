# Retrieval and Cohere reranking

## How many chunks go to the LLM?

- **Pipeline:** Hybrid search (vector + FTS) fetches many candidates → **Cohere rerank** picks the best K → those K chunks are sent to the LLM.
- **Config:** `CHUNKS_TO_LLM` (default **10**) = how many chunks the LLM sees. `SEARCH_CANDIDATES_FOR_RERANK` (default **30**) = how many candidates we send to the reranker.
- **Why not 20?** For legal reasoning, 5–12 chunks usually give enough context without noise or extra cost. More chunks can dilute focus and increase tokens. Default 10 is a good balance; increase only if answers feel missing context.
- **Tuning:** Set in `.env`: `CHUNKS_TO_LLM=8` or `CHUNKS_TO_LLM=12`. Run `make run` and test with real queries.

---

## What is Cohere reranking?

**Short:** Reranking takes a **query** and a **list of candidate texts** (from vector/FTS search) and **scores each candidate by relevance** to the query. We keep only the top K and send those to the LLM.

- **Why use it:** Vector search is fast but not perfect at “which chunk best answers this question?”. A reranker (e.g. Cohere) is trained to compare query vs passage and is better at relevance. So we fetch more candidates (e.g. 30), rerank them, then pass only the best 10 to the LLM.
- **In a legal reasoning system:** It keeps citations precise (the LLM sees the most relevant provisions/cases first), reduces irrelevant context, and helps avoid hallucination by feeding the model the right chunks. For Finnish we use a multilingual rerank model that supports Finnish.

---

## inotify watch limit (Streamlit)

If you see **`OSError: [Errno 28] inotify watch limit reached`** when running `make run` (Streamlit), the app still works; only file watching for live reload can fail. To fix the warning:

**Option A – increase system limit (Linux):**
```bash
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf && sudo sysctl -p
```

**Option B – disable file watcher (no live reload):**  
The project does this by default via `.streamlit/config.toml` and `make run`, so the terminal stays clean. Restart the app manually after code changes.
