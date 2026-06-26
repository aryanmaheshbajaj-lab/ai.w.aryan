"""ClinicBot V2 backend API tests - covers all endpoints in new architecture.

Auth model:
- Patient: phone+OTP via Twilio (dev mode returns dev_otp in /api/auth/send-otp)
- Doctor: email+password JWT (30 min idle), email=doctor@sharma.com pw=Doctor@123 (default)
"""
import os
from datetime import datetime, timedelta
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://bookhealth-app.preview.emergentagent.com').rstrip('/')
DOCTOR_EMAIL = "doctor@sharma.com"
DEFAULT_PASSWORD = "Doctor@123"
NEW_PASSWORD = "Test@1234"

# Mon=0..Sat=5 are open; Sunday closed
def _future_non_sunday(days_ahead_start=7):
    d = datetime.now().date() + timedelta(days=days_ahead_start)
    while d.weekday() == 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")

def _next_sunday():
    d = datetime.now().date() + timedelta(days=1)
    while d.weekday() != 6:
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# ---------------- Shared state ----------------
@pytest.fixture(scope="module")
def created():
    return {"appointments": [], "blocked_dates": []}


@pytest.fixture(scope="module")
def doctor_token():
    """Log in doctor; if default password rejected, try NEW_PASSWORD; if must_change → change to NEW_PASSWORD."""
    for pw in (DEFAULT_PASSWORD, NEW_PASSWORD):
        r = requests.post(f"{BASE_URL}/api/auth/doctor-login", json={"email": DOCTOR_EMAIL, "password": pw}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            tok = data["access_token"]
            if data.get("must_change_password"):
                # change password to NEW_PASSWORD
                rc = requests.post(f"{BASE_URL}/api/auth/doctor-change-password",
                                   json={"new_password": NEW_PASSWORD},
                                   headers={"Authorization": f"Bearer {tok}"},
                                   timeout=15)
                assert rc.status_code == 200, rc.text
                tok = rc.json()["access_token"]
            return tok
    pytest.skip(f"Doctor login failed for both default and new password")


@pytest.fixture(scope="module")
def patient_token():
    """Run OTP flow with a TEST phone number."""
    phone = "9000000099"
    r = requests.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": phone}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "dev_otp" in data, "Dev OTP should be returned in dev mode"
    otp = data["dev_otp"]
    r2 = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"phone": phone, "otp": otp}, timeout=15)
    assert r2.status_code == 200, r2.text
    return r2.json()["access_token"]


@pytest.fixture(scope="module", autouse=True)
def cleanup(created, doctor_token):
    yield
    h = {"Authorization": f"Bearer {doctor_token}"}
    for aid in created["appointments"]:
        try: requests.delete(f"{BASE_URL}/api/appointments/{aid}", headers=h, timeout=10)
        except Exception: pass
    for d in created["blocked_dates"]:
        try: requests.delete(f"{BASE_URL}/api/blocked-dates/{d}", headers=h, timeout=10)
        except Exception: pass


# ---------------- Health ----------------
class TestHealth:
    def test_root(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=10)
        assert r.status_code == 200
        assert r.json()["message"] == "ClinicBot API"


# ---------------- Auth ----------------
class TestAuth:
    def test_send_otp_returns_dev_otp(self):
        r = requests.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": "9999111122"}, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "dev_otp" in body
        assert len(body["dev_otp"]) == 6
        assert body["phone"] == "+919999111122"

    def test_verify_otp_invalid(self):
        # Send first to set state
        requests.post(f"{BASE_URL}/api/auth/send-otp", json={"phone": "9999111133"}, timeout=15)
        r = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={"phone": "9999111133", "otp": "000000"}, timeout=15)
        assert r.status_code in (400, 429)

    def test_doctor_login_wrong_password(self):
        r = requests.post(f"{BASE_URL}/api/auth/doctor-login", json={"email": DOCTOR_EMAIL, "password": "wrong-x"}, timeout=15)
        assert r.status_code == 401

    def test_doctor_login_success(self, doctor_token):
        assert doctor_token  # fixture passed
        # Decode roundtrip - calling /api/doctor/overview should succeed
        r = requests.get(f"{BASE_URL}/api/doctor/overview",
                         headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200, r.text


# ---------------- Clinic ----------------
class TestClinic:
    def test_get_clinic(self):
        r = requests.get(f"{BASE_URL}/api/clinic", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["name"] == "Little Stars Maternity Clinic"
        assert d["doctor_name"] == "Dr. Bhupendra"
        assert d["slot_duration"] == 15
        assert "_id" not in d

    def test_put_clinic_requires_doctor(self):
        r = requests.put(f"{BASE_URL}/api/clinic", json={"name": "X"}, timeout=15)
        assert r.status_code == 401

    def test_put_clinic_patient_forbidden(self, patient_token):
        r = requests.put(f"{BASE_URL}/api/clinic", json={"name": "X"},
                         headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r.status_code == 403

    def test_put_clinic_update(self, doctor_token):
        h = {"Authorization": f"Bearer {doctor_token}"}
        # update specialization, revert after
        orig = requests.get(f"{BASE_URL}/api/clinic", timeout=10).json()
        r = requests.put(f"{BASE_URL}/api/clinic", json={"specialization": "TEST_Pediatrics_Edit"}, headers=h, timeout=15)
        assert r.status_code == 200
        assert r.json()["specialization"] == "TEST_Pediatrics_Edit"
        # revert
        requests.put(f"{BASE_URL}/api/clinic", json={"specialization": orig["specialization"]}, headers=h, timeout=15)


# ---------------- Slots ----------------
class TestSlots:
    def test_slots_open(self):
        d = _future_non_sunday()
        r = requests.get(f"{BASE_URL}/api/slots", params={"date": d}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["closed"] is False
        # 11:00-14:00 with 15-min slots = 12
        assert len(body["slots"]) == 12
        assert body["slots"][0]["time"] == "11:00"

    def test_slots_sunday_closed(self):
        d = _next_sunday()
        r = requests.get(f"{BASE_URL}/api/slots", params={"date": d}, timeout=15)
        assert r.status_code == 200
        assert r.json()["closed"] is True

    def test_slots_invalid_date(self):
        r = requests.get(f"{BASE_URL}/api/slots", params={"date": "bad-date"}, timeout=15)
        assert r.status_code == 400


# ---------------- Appointments ----------------
class TestAppointments:
    def test_book_app_appointment(self, patient_token, created):
        date = _future_non_sunday(days_ahead_start=8)
        payload = {"patient_name": "TEST_PatientA", "problem": "TEST_cough",
                   "date": date, "time": "11:00", "source": "app"}
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload,
                          headers={"Authorization": f"Bearer {patient_token}"}, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "confirmed"
        assert body["source"] == "app"
        assert "_id" not in body
        created["appointments"].append(body["id"])

        # slot now booked
        rs = requests.get(f"{BASE_URL}/api/slots", params={"date": date}, timeout=15)
        slot = next(s for s in rs.json()["slots"] if s["time"] == "11:00")
        assert slot["available"] is False

    def test_double_book_409_with_suggestions(self, patient_token, doctor_token, created):
        date = _future_non_sunday(days_ahead_start=9)
        # First booking via doctor IVR
        p1 = {"patient_name": "TEST_IVR", "patient_phone": "9111111111", "problem": "TEST",
              "date": date, "time": "12:00", "source": "ivr"}
        r1 = requests.post(f"{BASE_URL}/api/appointments", json=p1,
                           headers={"Authorization": f"Bearer {doctor_token}"}, timeout=20)
        assert r1.status_code == 200
        created["appointments"].append(r1.json()["id"])

        # Patient now tries same slot
        p2 = {"patient_name": "TEST_Dup", "problem": "TEST", "date": date, "time": "12:00", "source": "app"}
        r2 = requests.post(f"{BASE_URL}/api/appointments", json=p2,
                           headers={"Authorization": f"Bearer {patient_token}"}, timeout=20)
        assert r2.status_code == 409
        detail = r2.json().get("detail")
        assert isinstance(detail, dict)
        assert "suggestions" in detail
        assert len(detail["suggestions"]) >= 1
        s = detail["suggestions"][0]
        assert "date" in s and "time" in s

    def test_ivr_requires_doctor_token(self, patient_token):
        date = _future_non_sunday(days_ahead_start=14)
        payload = {"patient_name": "TEST_IVRNoAuth", "patient_phone": "9888777666",
                   "problem": "TEST", "date": date, "time": "11:30", "source": "ivr"}
        # No token
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload, timeout=15)
        assert r.status_code == 401
        # With patient token - should also fail (IVR requires doctor)
        r2 = requests.post(f"{BASE_URL}/api/appointments", json=payload,
                           headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r2.status_code in (401, 403)

    def test_my_appointments(self, patient_token, created):
        date = _future_non_sunday(days_ahead_start=10)
        payload = {"patient_name": "TEST_Mine", "problem": "TEST",
                   "date": date, "time": "11:15", "source": "app"}
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload,
                          headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r.status_code == 200
        created["appointments"].append(r.json()["id"])

        r2 = requests.get(f"{BASE_URL}/api/appointments/my",
                          headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r2.status_code == 200
        data = r2.json()
        assert "upcoming" in data and "past" in data
        assert any(a["date"] == date and a["time"] == "11:15" for a in data["upcoming"])

    def test_all_appointments_doctor_masked(self, doctor_token):
        r = requests.get(f"{BASE_URL}/api/appointments/all", params={"scope": "all"},
                         headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200
        lst = r.json()
        assert isinstance(lst, list)
        if lst:
            assert "patient_phone_masked" in lst[0]
            assert "X" in lst[0]["patient_phone_masked"]

    def test_all_appointments_patient_forbidden(self, patient_token):
        r = requests.get(f"{BASE_URL}/api/appointments/all",
                         headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r.status_code == 403

    def test_mark_done(self, doctor_token, created):
        # Use doctor IVR booking for a fresh phone to avoid patient 2-future-appt limit
        date = _future_non_sunday(days_ahead_start=11)
        payload = {"patient_name": "TEST_Done", "patient_phone": "9555000111",
                   "problem": "TEST", "date": date, "time": "11:30", "source": "ivr"}
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload,
                          headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        created["appointments"].append(aid)
        rd = requests.patch(f"{BASE_URL}/api/appointments/{aid}/done",
                            headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert rd.status_code == 200

    def test_cancel(self, patient_token, doctor_token, created):
        date = _future_non_sunday(days_ahead_start=12)
        payload = {"patient_name": "TEST_Cancel", "patient_phone": "9123123123",
                   "problem": "TEST", "date": date, "time": "11:45", "source": "ivr"}
        r = requests.post(f"{BASE_URL}/api/appointments", json=payload,
                          headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200
        aid = r.json()["id"]
        rc = requests.delete(f"{BASE_URL}/api/appointments/{aid}", params={"reason": "TEST_reason"},
                             headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert rc.status_code == 200


# ---------------- Doctor overview & analytics ----------------
class TestDoctorAnalytics:
    def test_overview(self, doctor_token):
        r = requests.get(f"{BASE_URL}/api/doctor/overview",
                         headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["date", "total_today", "completed", "via_app", "via_phone"]:
            assert k in d

    def test_analytics(self, doctor_token):
        r = requests.get(f"{BASE_URL}/api/doctor/analytics",
                         headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["month_total", "month_app", "month_ivr", "by_dow", "by_hour",
                  "new_patients", "returning_patients", "cancellation_rate"]:
            assert k in d, f"missing {k}"
        assert isinstance(d["by_dow"], list)
        assert len(d["by_dow"]) == 7
        assert isinstance(d["by_hour"], list)

    def test_overview_requires_doctor(self):
        r = requests.get(f"{BASE_URL}/api/doctor/overview", timeout=10)
        assert r.status_code == 401


# ---------------- Recordings ----------------
class TestRecordings:
    def test_list_recordings_doctor(self, doctor_token):
        r = requests.get(f"{BASE_URL}/api/recordings",
                         headers={"Authorization": f"Bearer {doctor_token}"}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert "recordings" in body
        assert len(body["recordings"]) >= 5
        rec = body["recordings"][0]
        for k in ["id", "url", "caller_phone_masked", "duration_seconds", "transcript_preview"]:
            assert k in rec
        # masked
        assert "X" in rec["caller_phone_masked"]
        # Real URL
        assert rec["url"].startswith("http")

    def test_recordings_requires_doctor(self, patient_token):
        r = requests.get(f"{BASE_URL}/api/recordings",
                         headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r.status_code == 403


# ---------------- Blocked dates ----------------
class TestBlockedDates:
    def test_block_unblock(self, doctor_token, created):
        date = _future_non_sunday(days_ahead_start=20)
        h = {"Authorization": f"Bearer {doctor_token}"}
        r = requests.post(f"{BASE_URL}/api/blocked-dates",
                          json={"date": date, "reason": "TEST_Holiday"}, headers=h, timeout=15)
        assert r.status_code == 200, r.text
        created["blocked_dates"].append(date)
        # Slots closed
        rs = requests.get(f"{BASE_URL}/api/slots", params={"date": date}, timeout=15)
        assert rs.json()["closed"] is True
        # Unblock
        rd = requests.delete(f"{BASE_URL}/api/blocked-dates/{date}", headers=h, timeout=15)
        assert rd.status_code == 200
        created["blocked_dates"].remove(date)
        rs2 = requests.get(f"{BASE_URL}/api/slots", params={"date": date}, timeout=15)
        assert rs2.json()["closed"] is False

    def test_block_patient_forbidden(self, patient_token):
        r = requests.post(f"{BASE_URL}/api/blocked-dates",
                          json={"date": "2099-12-31", "reason": "x"},
                          headers={"Authorization": f"Bearer {patient_token}"}, timeout=15)
        assert r.status_code == 403


# ---------------- Auth guards ----------------
class TestAuthGuards:
    def test_unauth_doctor_endpoints(self):
        for url in ["/api/doctor/overview", "/api/doctor/analytics", "/api/recordings",
                    "/api/appointments/all"]:
            r = requests.get(f"{BASE_URL}{url}", timeout=10)
            assert r.status_code == 401, f"{url} should be 401, got {r.status_code}"

    def test_patient_cant_access_doctor(self, patient_token):
        h = {"Authorization": f"Bearer {patient_token}"}
        for url in ["/api/doctor/overview", "/api/doctor/analytics", "/api/recordings"]:
            r = requests.get(f"{BASE_URL}{url}", headers=h, timeout=10)
            assert r.status_code == 403, f"{url} expected 403, got {r.status_code}"
