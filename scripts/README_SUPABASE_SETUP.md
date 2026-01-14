# Supabase Database Setup Guide

## Prerequisites

1. **Supabase Account**: Create account at [supabase.com](https://supabase.com)
2. **Project Created**: Create a new Supabase project
3. **Environment Variables**: Add to your `.env` file:
   ```bash
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-or-service-key
   ```

## Setup Instructions

### Option 1: Using Supabase Dashboard (Recommended)

1. **Open SQL Editor**:
   - Go to your Supabase project dashboard
   - Click on "SQL Editor" in the left sidebar

2. **Run Setup Script**:
   - Copy the entire contents of `scripts/setup_supabase.sql`
   - Paste into the SQL Editor
   - Click "Run" button

3. **Verify Setup**:
   - Go to "Table Editor"
   - You should see `legal_chunks` table
   - Check "Database" → "Extensions" to confirm `vector` extension is enabled

### Option 2: Using Python Script

```python
from supabase import create_client
import os

# Initialize Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Read and execute SQL
with open("scripts/setup_supabase.sql", "r") as f:
    sql = f.read()
    # Note: Supabase Python client doesn't support raw SQL execution
    # Use the dashboard method instead
```

## Schema Overview

### Table: `legal_chunks`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `document_uri` | TEXT | Finlex document URI (for citations) |
| `document_title` | TEXT | Document title |
| `document_year` | INTEGER | Year of document |
| `document_type` | TEXT | Type (statute, decree, etc.) |
| `chunk_text` | TEXT | Actual text content |
| `chunk_index` | INTEGER | Order in document |
| `section_number` | TEXT | Legal section (e.g., "§ 3") |
| `embedding` | VECTOR(1536) | OpenAI text-embedding-3-small |
| `fts` | TSVECTOR | Full-text search vector (auto-generated) |
| `metadata` | JSONB | Additional context |
| `created_at` | TIMESTAMPTZ | Creation timestamp |
| `updated_at` | TIMESTAMPTZ | Last update timestamp |

### Indexes

1. **HNSW Vector Index**: Fast similarity search
2. **GIN FTS Index**: Fast full-text search
3. **URI Index**: Fast citation lookups
4. **Year Index**: Filter by time period
5. **Composite Index**: Document + chunk ordering

### Helper Functions

#### `vector_search(query_embedding, match_threshold, match_count)`
Performs semantic similarity search using pgvector.

**Example**:
```sql
SELECT * FROM vector_search(
    '[0.1, 0.2, ...]'::vector(1536),
    0.5,  -- similarity threshold
    50    -- top 50 results
);
```

#### `fts_search(query_text, match_count)`
Performs full-text search with BM25-like ranking.

**Example**:
```sql
SELECT * FROM fts_search(
    'työnantajan & velvollisuudet',
    50  -- top 50 results
);
```

## Testing the Setup

### 1. Insert Test Data

```sql
INSERT INTO legal_chunks (
    document_uri,
    document_title,
    document_year,
    document_type,
    chunk_text,
    chunk_index,
    section_number
) VALUES (
    'https://finlex.fi/fi/laki/ajantasa/2025/20250001',
    'Rahoituslaki',
    2025,
    'statute',
    'Työnantajan on huolehdittava työntekijöiden turvallisuudesta.',
    0,
    '§ 1'
);
```

### 2. Verify FTS Auto-Generation

```sql
SELECT chunk_text, fts 
FROM legal_chunks 
WHERE id = (SELECT id FROM legal_chunks LIMIT 1);
```

The `fts` column should be automatically populated!

### 3. Test Full-Text Search

```sql
SELECT * FROM fts_search('työnantajan', 10);
```

### 4. Check Statistics

```sql
SELECT * FROM document_stats;
```

## Troubleshooting

### Error: "extension vector does not exist"

**Solution**: Enable the vector extension manually:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### Error: "permission denied for schema public"

**Solution**: You need to use the service role key (not anon key) for schema modifications. Find it in:
- Supabase Dashboard → Settings → API → service_role key

### FTS not working for Finnish text

**Solution**: Verify Finnish language support:
```sql
SELECT * FROM pg_ts_config WHERE cfgname = 'finnish';
```

If not available, the schema will fall back to 'simple' configuration.

## Next Steps

After setup is complete:

1. ✅ **Step 1 Complete**: Database schema ready
2. ⏭️ **Step 2**: Create chunking service
3. ⏭️ **Step 3**: Create embedding service
4. ⏭️ **Step 4**: Build ingestion pipeline

## Security Notes

- **Row Level Security (RLS)** is enabled by default
- Public read access is allowed
- Insert/update/delete requires authentication
- Adjust policies in `setup_supabase.sql` based on your needs

## Maintenance

### Remove Duplicate Chunks
```sql
SELECT remove_duplicate_chunks();
```

### Reindex Vectors (if needed)
```sql
REINDEX INDEX legal_chunks_embedding_idx;
```

### Update Statistics
```sql
ANALYZE legal_chunks;
```
