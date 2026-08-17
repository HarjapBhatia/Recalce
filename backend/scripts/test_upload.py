import requests
import time
import sys
from pathlib import Path

BASE_URL = "http://localhost:8000/api/v1"
BACKEND_DIR = Path(__file__).resolve().parents[1]
INTERNAL_LEDGER = BACKEND_DIR / "tests" / "fixtures" / "internal_ledger_test.csv"
BANK_STATEMENT = BACKEND_DIR / "tests" / "fixtures" / "bank_statement_test.csv"

def test_upload():
    print("Uploading 5,000-row batch...")
    
    with INTERNAL_LEDGER.open("rb") as f_internal, \
         BANK_STATEMENT.open("rb") as f_bank:
        
        files = {
            "internal_ledger": ("internal_ledger_test.csv", f_internal, "text/csv"),
            "bank_statement": ("bank_statement_test.csv", f_bank, "text/csv")
        }
        
        response = requests.post(f"{BASE_URL}/upload", files=files)
        
    if response.status_code != 202:
        print(f"Failed to upload: {response.text}")
        sys.exit(1)
        
    data = response.json()
    batch_id = data["batch_id"]
    print(f"Upload successful. Batch ID: {batch_id}")
    
    # Poll for status
    start_time = time.time()
    while True:
        res = requests.get(f"{BASE_URL}/status/{batch_id}")
        if res.status_code == 200:
            status_data = res.json()
            status = status_data["status"]
            print(f"[{time.time() - start_time:.1f}s] Status: {status}")
            
            if status in ["COMPLETE", "FAILED", "ML_TRIAGE"]:
                print(f"Final status reached: {status}")
                if status == "FAILED":
                    print(f"Error: {status_data.get('error_message')}")
                break
        else:
            print(f"Failed to get status: {res.text}")
            break
            
        time.sleep(2)
        
    # Get results summary
    if status in ["COMPLETE", "ML_TRIAGE"]:
        print("Fetching results...")
        res = requests.get(f"{BASE_URL}/results/{batch_id}")
        if res.status_code == 200:
            results = res.json()
            total_matches = len(results.get("results", []))
            print(f"Successfully fetched {total_matches} result records.")
        else:
            print(f"Failed to fetch results: {res.text}")

if __name__ == "__main__":
    test_upload()
