# LangGraph Agent Architecture

## Overview

The AI Legal Reasoning System uses **LangGraph** as the orchestration layer for processing user queries through a multi-stage workflow.

## Architecture Flow

```
User Query
    ↓
[ANALYZE] Extract intent & entities (future: TurkuNLP/FinBERT)
    ↓
[SEARCH] Retrieve relevant documents (future: Neo4j + Supabase)
    ↓
[REASON] Apply legal reasoning (future: GPT-4o)
    ↓
[RESPOND] Generate final response
    ↓
Streamlit UI
```

## Components

### 1. State Management ([state.py](file:///home/dev/AI%20Legal%20Reasoing%20system/src/agent/state.py))

**AgentState** tracks data through the workflow:
- `query`: User input
- `messages`: Chat history
- `stage`: Current processing stage
- `search_results`: Retrieved documents (placeholder)
- `entities`: Extracted legal entities (placeholder)
- `response`: Final output
- `error`: Error tracking

### 2. Processing Nodes ([nodes.py](file:///home/dev/AI%20Legal%20Reasoing%20system/src/agent/nodes.py))

Each node is an **abstraction layer** for future integrations:

**`analyze_query(state)`**
- Current: Mock entity extraction
- Future: TurkuNLP/FinBERT for Finnish NLP

**`search_knowledge(state)`**
- Current: Mock search results
- Future: Query Neo4j graph + Supabase vectors

**`reason_legal(state)`**
- Current: Placeholder
- Future: GPT-4o legal reasoning

**`generate_response(state)`**
- Current: Mock formatted response
- Future: Streamed LLM responses

**`handle_error(state)`**
- Error handling for workflow failures

### 3. Workflow Graph ([graph.py](file:///home/dev/AI%20Legal%20Reasoing%20system/src/agent/graph.py))

Defines the **sequential flow**:
```
START → analyze → search → reason → respond → END
```

Uses **LangGraph StateGraph** for orchestration.

### 4. Agent Interface ([agent.py](file:///home/dev/AI%20Legal%20Reasoing%20system/src/agent/agent.py))

**`process_query(user_query, chat_history)`**
- Main entry point
- Initializes state
- Runs workflow
- Returns response

**`get_agent_info()`**
- System status and integration info

## Integration Points

### Current (MVP)
✅ LangGraph workflow active  
✅ Streamlit UI connected  
✅ Mock responses showing workflow stages

### Future Integrations

**Phase 3: Document Processing**
- Replace `analyze_query` mock with TurkuNLP/FinBERT
- Add Finlex API document fetching

**Phase 4: Knowledge Storage**
- Replace `search_knowledge` mock with Neo4j + Supabase queries
- Implement vector similarity search

**Phase 5: LLM Reasoning**
- Replace `reason_legal` and `generate_response` with GPT-4o
- Add streaming responses

## Testing the Agent

### 1. Run Streamlit UI
```bash
streamlit run src/ui/app.py
```

### 2. Test Query
Type any legal question - the agent will show:
- Query analysis status
- Workflow stage progression
- Mock response with integration roadmap

### 3. Verify Workflow
Check sidebar message count increases by 2 (user + assistant).

## Adding New Integration

**Example: Adding GPT-4o**

1. Update [`nodes.py`](file:///home/dev/AI%20Legal%20Reasoing%20system/src/agent/nodes.py):
```python
def reason_legal(state: AgentState) -> AgentState:
    from openai import OpenAI
    client = OpenAI()
    
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": state["query"]}]
    )
    
    state["response"] = response.choices[0].message.content
    return state
```

2. No changes needed to graph or UI - abstraction layer handles it!

## File Structure

```
src/agent/
├── state.py       # Data structure definition
├── nodes.py       # Processing functions (abstraction layer)
├── graph.py       # Workflow definition
└── agent.py       # Main interface
```

## Design Principles

1. **Abstraction**: Each node is a placeholder for future complex logic
2. **Modularity**: Easy to swap mock implementations with real ones
3. **Stateful**: All data flows through AgentState
4. **Sequential**: Clear linear workflow (can expand to conditional later)
5. **Testable**: Each node can be tested independently

---

**Status:** ✅ Abstraction layer complete, ready for integration
