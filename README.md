# AI Legal Reasoning System

Finnish legal document analysis and reasoning platform.

## Project Structure

```
AI Legal Reasoing system/
├── src/
│   ├── ui/
│   │   └── app.py              # Streamlit chat interface
│   ├── config/
│   │   └── settings.py         # Configuration constants
│   └── utils/
│       └── chat_helpers.py     # Chat utility functions
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Setup

### Option 1: Automated Setup (Recommended)

```bash
./setup.sh
```

This will:
- Check Python installation
- Install pip if needed (requires sudo)
- Install all dependencies

### Option 2: Manual Setup

#### 1. Install pip (if not installed)

```bash
sudo apt update && sudo apt install -y python3-pip
```

#### 2. Install Dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Run Application

```bash
streamlit run src/ui/app.py
```

The app will open at `http://localhost:8501`

## Current Status

✅ **Phase 1:** Streamlit chat UI (Complete)
⏳ **Phase 2:** Finlex API integration (Pending)
⏳ **Phase 3:** LangGraph agent (Pending)
⏳ **Phase 4:** Neo4j + Supabase storage (Pending)

## MVP Scope

- **Year Range:** 2025
- **Document Categories:** Acts, Judgments, Docs
- **Language:** Finnish
- **NLP Model:** TurkuNLP/FinBERT (pre-trained)

## Tech Stack

- **UI:** Streamlit
- **Workflows:** LangGraph (pending)
- **LLM:** GPT-4o (pending)
- **Graph DB:** Neo4j (pending)
- **Vector DB:** Supabase pgvector (pending)
- **Embeddings:** Voyage AI (pending)
