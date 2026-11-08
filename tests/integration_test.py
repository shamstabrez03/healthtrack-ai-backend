import requests
import json
from datetime import date, timedelta

BASE_URL = "http://127.0.0.1:8000"

def run_integration_tests():
    print("=== 1. Health Check ===")
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    print("  -> Backend is healthy:", r.json())

    print("\n=== 2. User Registration ===")
    email = f"testuser_{int(date.today().strftime('%Y%m%d'))}@example.com"
    reg_payload = {
        "name": "Dr. Shams Tabrez",
        "email": email,
        "password": "SecurePassword123!"
    }
    # Try register, if already exists login
    r = requests.post(f"{BASE_URL}/api/auth/register", json=reg_payload)
    if r.status_code == 400 and "already registered" in r.text:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": reg_payload["password"]})
    
    assert r.status_code == 200, f"Auth failed: {r.text}"
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("  -> Auth token acquired successfully!")

    print("\n=== 3. Current User Profile ===")
    r = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    assert r.status_code == 200
    user_data = r.json()
    print("  -> User profile:", user_data["name"], f"({user_data['email']})")

    print("\n=== 4. Family Member Management ===")
    r = requests.get(f"{BASE_URL}/api/family", headers=headers)
    assert r.status_code == 200
    family = r.json()
    print("  -> Existing profiles count:", len(family))
    self_patient = next((p for p in family if p["relationship_type"] == "self"), family[0])
    print("  -> Self profile ID:", self_patient["id"], self_patient["name"])

    # Create Father profile
    father_payload = {
        "name": "Mohammad (Father)",
        "relationship_type": "father",
        "date_of_birth": "1965-05-15",
        "gender": "male"
    }
    r = requests.post(f"{BASE_URL}/api/family", json=father_payload, headers=headers)
    assert r.status_code == 201
    father_patient = r.json()
    print("  -> Created family profile:", father_patient["name"], f"ID: {father_patient['id']}")

    print("\n=== 5. Dashboard State Verification ===")
    r = requests.get(f"{BASE_URL}/api/dashboard", params={"patient_id": self_patient["id"]}, headers=headers)
    assert r.status_code == 200
    dashboard = r.json()
    print("  -> Dashboard loaded:")
    print("     - Patient:", dashboard["patient_name"])
    print("     - Reports Count:", dashboard["report_count"])
    print("     - Tracked Tests:", dashboard["tracked_test_count"])
    print("     - Needs Attention:", dashboard["attention_count"])

    print("\n=== 6. Verify Settings & Key Security ===")
    r = requests.get(f"{BASE_URL}/api/settings/gemini", headers=headers)
    assert r.status_code == 200
    settings_data = r.json()
    print("  -> Gemini settings:", settings_data)
    assert "api_key" not in settings_data, "API key should NEVER be exposed in responses!"

    print("\n=== ALL INTEGRATION CHECKS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_integration_tests()
