#!/usr/bin/env python3
"""
Seeder script to populate failed_documents table for testing retry-failed endpoint

Usage:
    python3 scripts/seed_failed_documents.py          # Insert test data
    python3 scripts/seed_failed_documents.py --clean  # Remove test data
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.supabase import SupabaseStorage


def seed_failed_documents():
    """Insert test failed documents into the database"""
    storage = SupabaseStorage()
    
    # Test documents with different retry counts using REAL Finlex URIs
    test_documents = [
        {
            "document_uri": "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/1/fin@",
            "error_message": "Test error: Simulated API timeout",
            "error_type": "api_error",
            "document_category": "act",
            "document_type": "statute",
            "document_year": 2025,
            "language": "fin",
            "retry_count": 0
        },
        {
            "document_uri": "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/2/swe@",
            "error_message": "Test error: Simulated XML parsing failure",
            "error_type": "parsing_error",
            "document_category": "act",
            "document_type": "statute",
            "document_year": 2025,
            "language": "swe",
            "retry_count": 1
        },
        {
            "document_uri": "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/3/fin@",
            "error_message": "Test error: Simulated embedding generation failure",
            "error_type": "embedding_error",
            "document_category": "act",
            "document_type": "statute",
            "document_year": 2025,
            "language": "eng",
            "retry_count": 2
        },
        {
            "document_uri": "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/4/fin@",
            "error_message": "Test error: Max retries reached",
            "error_type": "api_error",
            "document_category": "act",
            "document_type": "statute",
            "document_year": 2025,
            "language": "fin",
            "retry_count": 3  # This one should NOT be retried (already at max)
        }
    ]
    
    print("🌱 Seeding failed_documents table...\n")
    
    inserted = 0
    updated = 0
    errors = 0
    
    for doc in test_documents:
        try:
            # Check if already exists
            existing = storage.client.table('failed_documents').select('*').eq(
                'document_uri', doc['document_uri']
            ).execute()
            
            if existing.data:
                # Update existing
                storage.client.table('failed_documents').update(doc).eq(
                    'document_uri', doc['document_uri']
                ).execute()
                updated += 1
                print(f"🔄 Updated: {doc['document_uri']}")
            else:
                # Insert new
                storage.client.table('failed_documents').insert(doc).execute()
                inserted += 1
                print(f"✅ Inserted: {doc['document_uri']}")
            
            print(f"   └─ retry_count: {doc['retry_count']}, language: {doc['language']}, error: {doc['error_message']}\n")
            
        except Exception as e:
            errors += 1
            print(f"❌ Error: {doc['document_uri']}")
            print(f"   └─ {str(e)}\n")
    
    print("=" * 80)
    print(f"📊 SEEDING COMPLETE: {inserted} inserted, {updated} updated, {errors} errors")
    print("=" * 80)
    
    if inserted > 0 or updated > 0:
        print("\n✅ Test data ready!")
        print("\n🧪 HOW TO TEST /retry-failed:")
        print("\n1. Ensure API is running:")
        print("   python3 src/api/ingest.py")
        print("\n2. Send POST request to: http://localhost:8000/retry-failed")
        print("   Body: {\"max_retries\": 3}")
        print("\n3. Expected: 3 documents retried (retry_count < 3)")
        print("   - Document 1 (retry_count=0) → will retry")
        print("   - Document 2 (retry_count=1) → will retry")
        print("   - Document 3 (retry_count=2) → will retry")
        print("   - Document 4 (retry_count=3) → will be SKIPPED")
        print("\n4. After retry, check retry_counts incremented in database")
        print("=" * 80 + "\n")


def clean_failed_documents():
    """Remove test failed documents from the database"""
    storage = SupabaseStorage()
    
    test_uris = [
        "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/1/fin@",
        "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/2/swe@",
        "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/3/eng@",
        "https://opendata.finlex.fi/finlex/avoindata/v1/akn/fi/act/statute/2025/4/fin@"
    ]
    
    print("🧹 Cleaning test data from failed_documents...\n")
    
    deleted = 0
    errors = 0
    
    for uri in test_uris:
        try:
            result = storage.client.table('failed_documents').delete().eq(
                'document_uri', uri
            ).execute()
            deleted += 1
            print(f"✅ Deleted: {uri}")
        except Exception as e:
            errors += 1
            print(f"❌ Error deleting {uri}: {str(e)}")
    
    print(f"\n✨ Cleanup complete: {deleted} deleted, {errors} errors\n")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Seed failed_documents table for testing")
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Remove test documents instead of inserting them'
    )
    
    args = parser.parse_args()
    
    if args.clean:
        clean_failed_documents()
    else:
        seed_failed_documents()
