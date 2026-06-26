"""ClinicBot backend API tests."""
import os
from datetime import datetime, timedelta
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://bookhealth-app.preview.emergentagent.com').rstrip('/')
DOCTOR_PASSWORD = "Aryan95@"


def _future_non_sunday(days_ahead_start=7):
    """Return a future date string that is not Sunday."""
    d = datetime.now().date() + timedelta(days=days_ahead_start)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def _next_sunday():
    d = datetime.now().date() + timedelta(days=1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


@pytest.fixture(scope="module")
def created_ids():
    return {"appointments": [], "blocked_dates": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup_after(created_ids):
    yield
    # Cleanup created appointments
    for aid in created_ids["appointments"]:
        try:
            requests.delete(f"{BASE_URL}/api/appointments/{aid}", timeout=10)
        except Exception:
            pass
    for d in created_ids["blocked_dates"]:
        try:
            requests.delete(f"{BASE_URL}/api/blocked-dates/{d}", timeout=10)
        except Exception:
            pass


# ===== Clinic info =====
class TestClinicInfo:
    def test_clinic_info(self):
        r = requests.get(f"{BASE_URL}/api/clinic/info", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "Dr. Sharma Clinic"
        assert data["doctor_name"] == "Dr. Sharma"
        assert data["morning_start"] == "10:00"
        assert data["morning_end"] == "14:00"
        assert data["evening_start"] == "17:00"
        assert data["evening_end"] == "20:00"
        assert data["closed_day"] == 6
        assert data["slot_duration_minutes"] == 30
        assert "_id" not in data


# ===== Slots =====
class TestSlots:
    def test_slots_normal_day(self):
        d = _future_non_sunday()
        r = requests.get(f"{BASE_URL}/api/slots/{d}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["closed"] is False
        # Morning 10-14 = 8 slots; Evening 17-20 = 6 slots = 14 total
        assert len(data["slots"]) == 14
        s = data["slots"][0]
        assert "time" in s and "available" in s and "period" in s
        assert "_id" not in data

    def test_slots_sunday_closed(self):
        d = _next_sunday()
        r = requests.get(f"{BASE_URL}/api/slots/{d}", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["closed"] is True
        assert data["slots"] == []

    def test_slots_invalid_date(self):
        r = requests.get(f"{BASE_URL}/api/slots/not-a-date", timeout=15)
        assert r.status_code == 400


# ===== Appointments =====
class TestAppointments:
    def test_create_and_persist(self, created_ids):
        date = _future_non_sunday(days_ahead_start=8)
        payload = {
            "patient_name": "TEST_Aryan",
            "patient_phone": "9876543210",
            "problem": "TEST_fever",
            "date": date,
            "time": "10:00",
            "source": "app",
        }
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["patient_name"] == "TEST_Aryan"
        assert body["status"] == "confirmed"
        assert "_id" not in body
        created_ids["appointments"].append(body["id"])

        # GET slots - confirm 10:00 now unavailable
        r2 = requests.get(f"{BASE_URL}/api/slots/{date}", timeout=15)
        slot_10 = next(s for s in r2.json()["slots"] if s["time"] == "10:00")
        assert slot_10["available"] is False

    def test_double_booking_returns_409_with_next(self, created_ids):
        date = _future_non_sunday(days_ahead_start=9)
        payload = {
            "patient_name": "TEST_DoubleA",
            "patient_phone": "9876500001",
            "problem": "TEST",
            "date": date, "time": "11:00", "source": "app",
        }
        r1 = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=20)
        assert r1.status_code == 200
        created_ids["appointments"].append(r1.json()["id"])

        payload["patient_name"] = "TEST_DoubleB"
        r2 = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=20)
        assert r2.status_code == 409
        detail = r2.json().get("detail")
        # FastAPI wraps non-string detail; "next" should be nested
        assert isinstance(detail, dict)
        assert "next" in detail
        assert detail["next"].get("time") is not None

    def test_upcoming(self, created_ids):
        date = _future_non_sunday(days_ahead_start=10)
        payload = {
            "patient_name": "TEST_Upcoming", "patient_phone": "9876500002",
            "problem": "TEST", "date": date, "time": "12:00", "source": "app"
        }
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=20)
        assert r.status_code == 200
        created_ids["appointments"].append(r.json()["id"])

        r2 = requests.get(f"{BASE_URL}/api/appointments/upcoming", timeout=15)
        assert r2.status_code == 200
        lst = r2.json()
        assert any(a["date"] == date and a["time"] == "12:00" for a in lst)
        for a in lst:
            assert a["status"] == "confirmed"
            assert "_id" not in a

    def test_today_endpoint(self):
        r = requests.get(f"{BASE_URL}/api/appointments/today", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_cancel_frees_slot(self, created_ids):
        date = _future_non_sunday(days_ahead_start=11)
        payload = {
            "patient_name": "TEST_Cancel", "patient_phone": "9876500003",
            "problem": "TEST", "date": date, "time": "13:00", "source": "app"
        }
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=20)
        assert r.status_code == 200
        aid = r.json()["id"]

        # cancel
        rc = requests.delete(f"{BASE_URL}/api/appointments/{aid}", timeout=15)
        assert rc.status_code == 200

        # slot is free again
        rs = requests.get(f"{BASE_URL}/api/slots/{date}", timeout=15)
        slot = next(s for s in rs.json()["slots"] if s["time"] == "13:00")
        assert slot["available"] is True

    def test_ivr_blocks_app(self, created_ids):
        date = _future_non_sunday(days_ahead_start=12)
        payload = {
            "patient_name": "TEST_IVR", "patient_phone": "9876500004",
            "problem": "TEST_phone", "date": date, "time": "10:30", "source": "ivr"
        }
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=20)
        assert r.status_code == 200
        created_ids["appointments"].append(r.json()["id"])
        assert r.json()["source"] == "ivr"

        # Now app booking for same slot must fail
        payload2 = dict(payload, patient_name="TEST_AppOver", source="app")
        r2 = requests.post(f"{BASE_URL}/api/appointments", json=payload2, timeout=20)
        assert r2.status_code == 409


# ===== Doctor =====
class TestDoctor:
    def test_doctor_login_success(self):
        r = requests.post(f"{BASE_URL}/api/doctor/login", json={"password": DOCTOR_PASSWORD}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_doctor_login_wrong(self):
        r = requests.post(f"{BASE_URL}/api/doctor/login", json={"password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_doctor_stats(self):
        r = requests.get(f"{BASE_URL}/api/doctor/stats", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "today" in data and "total" in data
        assert isinstance(data["today"], int)
        assert isinstance(data["total"], int)


# ===== Blocked dates =====
class TestBlockedDates:
    def test_block_and_unblock(self, created_ids):
        date = _future_non_sunday(days_ahead_start=20)
        # Block
        r = requests.post(f"{BASE_URL}/api/blocked-dates", json={"date": date, "reason": "TEST_Holiday"}, timeout=15)
        assert r.status_code == 200, r.text
        created_ids["blocked_dates"].append(date)
        assert r.json()["reason"] == "TEST_Holiday"

        # slots returns closed
        rs = requests.get(f"{BASE_URL}/api/slots/{date}", timeout=15)
        data = rs.json()
        assert data["closed"] is True
        assert "TEST_Holiday" in (data.get("reason") or "")

        # Unblock
        rd = requests.delete(f"{BASE_URL}/api/blocked-dates/{date}", timeout=15)
        assert rd.status_code == 200
        created_ids["blocked_dates"].remove(date)

        # slots back to open
        rs2 = requests.get(f"{BASE_URL}/api/slots/{date}", timeout=15)
        assert rs2.json()["closed"] is False
