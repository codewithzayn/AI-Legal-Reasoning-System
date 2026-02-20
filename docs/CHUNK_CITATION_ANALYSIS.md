# Why the LLM Cites Only 2–4 of 12 Retrieved Chunks

## Problem

- Pipeline sends **12 chunks** to the LLM (after Cohere rerank + diversity cap).
- LLM uses/cites only **2–4** in its answer.
- Fraud and civil cases often work well; other domains (administrative, tax, etc.) underperform.
- Relevant documents seem to be omitted instead of cited.

---

## Root Causes

### 1. **Smart diversity cap: max 2 chunks per case**

```text
_smart_diversity_cap(max_per_case=2, top_k=12)
```

- Top 2 chunks are uncapped; then at most **2 chunks per case**.
- If many strong matches come from the same case, extra chunks from that case are dropped.
- Result: retrieval may drop highly relevant chunks before they reach the LLM, especially when a single case dominates results.
- Fraud/civil: often multiple distinct cases → less impact.
- Other domains: fewer cases, more chunks per case → more loss due to cap.

### 2. **LLM selectivity and prompt**

- Prompt says “use the provided context” and “every claim must cite,” but not “cite every relevant source.”
- Emphasis on “most relevant” and “focus on asked case” pushes the model toward a small set of sources.
- Model has natural tendency to prefer fewer, stronger citations.

### 3. **Response length limit (800 tokens)**

- `max_tokens=800` constrains how much the model can write.
- Discussing and citing 12 cases in 800 tokens is difficult; 2–4 cases is more realistic.
- More chunks → higher risk of truncation and incomplete citations.

### 4. **Context position bias**

- Models often focus more on the start and end of the context.
- Chunks in positions 5–10 may be underused even if relevant.
- 12 chunks increase the chance that useful chunks sit in weaker positions.

### 5. **Domain and embedding mismatch**

- Fraud/civil: clear terms (petos, kavallus, vahingonkorvaus) that embed well.
- Other domains (e.g. administrative, tax, employment): different vocabulary and structure.
- Embeddings and reranker may rank these chunks lower, so they appear in weaker positions or get cut by the diversity cap.

---

## Recommended Fixes (priority order)

| # | Fix | Impact | Effort |
|---|-----|--------|--------|
| 1 | Raise `max_per_case` to 3–4 (or make configurable) | More relevant chunks from strong cases reach the LLM | Low |
| 2 | Add explicit prompt instruction: “Cite all relevant cases from the context that support your answer; do not limit to 2–3.” | Encourages use of more sources | Low |
| 3 | Increase `max_tokens` to 1200–1500 | Room for more cases and citations | Low |
| 4 | Consider MMR-style diversity in retrieval instead of strict per-case cap | Balance relevance and diversity without hard 2-per-case limit | Medium |
| 5 | Add per-domain tuning or separate configs (e.g. fraud vs administrative) | Handles domain-specific behavior | Medium |

---

## Short summary

- **Retrieval**: The per-case cap (`max_per_case=2`) likely drops relevant chunks, especially when results are dominated by a few cases.
- **LLM**: Prompt and 800-token limit encourage focusing on 2–4 sources instead of using all 12.
- **Domain**: Embeddings and reranker favor fraud/civil terms; other domains may be ranked lower and hit the cap more often.

Start with fixes #1–3 for fastest impact.
