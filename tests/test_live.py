import urllib.request
import urllib.parse
import time
import sys

def test_live_server():
    print("=== STARTING LIVE SERVER HTTP TEST ===")
    
    # 1. POST paste scan request
    post_data = urllib.parse.urlencode({
        "code": "import sqlite3\ndef unsafe(user):\n    conn = sqlite3.connect('test.db')\n    conn.execute('select * from users where name = ' + user)"
    }).encode("utf-8")
    
    req = urllib.request.Request("http://127.0.0.1:8000/api/scan", data=post_data, method="POST")
    try:
        response = urllib.request.urlopen(req)
    except Exception as e:
        print(f"FAILED to POST scan: {e}")
        sys.exit(1)
        
    final_url = response.geturl()
    print(f"HTTP Redirect URL: {final_url}")
    scan_id = final_url.split("/")[-1]
    print(f"Extracted Scan ID: {scan_id}")
    
    # 2. Poll Status until completed
    completed = False
    for i in range(15):
        try:
            status_resp = urllib.request.urlopen(f"http://127.0.0.1:8000/scans/{scan_id}/status")
            html = status_resp.read().decode("utf-8")
            
            if "Vulnerability Log" in html or "v-item" in html or "dashboard_metrics" in html or "total_issues" in html or "findings" in html:
                print(f"Scan completed successfully at poll #{i+1}!")
                completed = True
                break
            elif "Scan Execution Failed" in html:
                print("Scan status reported FAILURE!")
                sys.exit(1)
            else:
                print(f"Scan is running... polling #{i+1}")
                time.sleep(2)
        except Exception as e:
            print(f"Polling error: {e}")
            sys.exit(1)
            
    if not completed:
        print("ERROR: Scan did not complete within timeout.")
        sys.exit(1)
        
    print("=== LIVE SERVER TEST PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    test_live_server()
