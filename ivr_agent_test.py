import requests

BACKEND_URL = "https://aiwaryan-production.up.railway.app"
DOCTOR_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkb2N0b3JAc2hhcm1hLmNvbSIsInJvbGUiOiJkb2N0b3IiLCJpYXQiOjE3ODI1ODUwODAsImV4cCI6MTc4MjU4Njg4MH0.79pTU4t_yAUwt0Mog4F7IPKd0GZ0qU5dTg2oJ6y7vYE"   # Paste your doctor token

def test_booking():
    payload = {
        "patient_name": "Test Child",
        "patient_phone": "9876543210",
        "problem": "Fever",
        "date": "2026-06-28",
        "time": "11:00",
        "source": "ivr"
    }
    headers = {"Authorization": f"Bearer {DOCTOR_TOKEN}"}
    r = requests.post(f"{BACKEND_URL}/api/appointments", json=payload, headers=headers)
    print("Status Code:", r.status_code)
    print("Response:", r.json())

test_booking()
