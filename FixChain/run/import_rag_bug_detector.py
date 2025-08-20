#!/usr/bin/env python3
"""
Script to import RAG bug detector data via API endpoint
"""

import json
import requests
from pathlib import Path

def import_rag_bug_detector():
    """Import all RAG bug detector documents via API"""
    # Load sample data
    sample_file = Path(__file__).parent.parent / "mocks" / "sample_rag_bug_detector.json"
    
    with open(sample_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    api_url = "http://localhost:8000/api/v1/rag/reasoning/add"
    headers = {'Content-Type': 'application/json'}
    
    success_count = 0
    total_count = len(data)
    
    print(f"Importing {total_count} RAG bug detector documents...")
    
    for i, doc in enumerate(data, 1):
        try:
            payload = {
                "content": doc["content"],
                "metadata": doc["metadata"]
            }
            
            response = requests.post(api_url, json=payload, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                print(f"✓ Document {i}/{total_count} imported: {result['document_id']}")
                success_count += 1
            else:
                print(f"✗ Failed to import document {i}/{total_count}: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"✗ Error importing document {i}/{total_count}: {str(e)}")
    
    print(f"\nImport completed: {success_count}/{total_count} documents imported successfully")
    
    # Check final stats
    try:
        stats_response = requests.get("http://localhost:8000/api/v1/rag/reasoning/stats")
        if stats_response.status_code == 200:
            stats = stats_response.json()
            print(f"Total documents in RAG system: {stats['document_count']}")
    except Exception as e:
        print(f"Could not retrieve stats: {str(e)}")

if __name__ == "__main__":
    import_rag_bug_detector()