from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging, random, uuid
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import jwt, bcrypt
from jwt import ExpiredSignatureError, InvalidTokenError
from datetime import datetime, timezone, timedelta


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds OWASP-recommended security headers to every response."""
    CSP = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' https:; "
        "connect-src 'self' https: wss:; "
        "frame-ancestors 'none'"
    )
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = self.CSP
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

VOICELINK_REGISTRATION_PASSWORD = os.environ.get('VOICELINK_REGISTRATION_PASSWORD', '')
VOICELINK_USERNAME = os.environ.get('VOICELINK_USERNAME', '')
VOICELINK_SERVER_PORT= os.environ.get('vOICELINK_SERVER_PORT', '')
VOICELINK_SIP_SERVER = os.environ.get('VOICELINK_SIP_SERVER','')
JWT_SECRET = os.environ.get('JWT_SECRET', 'change-me')
JWT_ALG = os.environ.get('JWT_ALGORITHM', 'HS256')
DOCTOR_EMAIL = os.environ.get('DOCTOR_EMAIL', 'doctor@sharma.com')
DOCTOR_DEFAULT_PASSWORD = os.environ.get('DOCTOR_DEFAULT_PASSWORD', 'Doctor@123')
IVR_SECRET = os.environ.get('IVR_SECRET', 'change-me-ivr')
OTP_DEV_MODE = os.environ.get('OTP_DEV_MODE', 'true').lower() == 'true'

try:
    from voicelink.rest import Client as VoicelinkClient
    voicelink_client = VoicelinkClient(VOICELINK_USERNAME,VOICELINK_REGISTRATION_PASSWORD) if VOICELINK_USERNAME and VOICELINK_REGISTRATION_PASSWORD else None
except Exception:
    voicelink_client = None

app = FastAPI()
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_CLINIC = {
    "id": "default",
    "name": "Little Stars Child Clinic",
    "doctor_name": "Dr. Bhupendra Asudani",
    "specialization": "Pediatrician",
    "qualifications": "MBBS — Panjabrao Deshmukh Memorial Medical College (2010); DCH — Lata Mangeshkar Medical College, Nagpur (2012)",
    "experience_years": 5,
    "address": "MIG 63, Housing Board Colony, opposite Durge Atta Chakki, Near Bhim Chowk, Nara Road, Jaripatka, Nagpur, Maharashtra 440014",
    "phone": "+919699510023",
    "emergency_phone": "+919373827701",
    "consultation_fee": 400,
    "morning_start": "11:00",
    "morning_end": "14:00",
    "evening_start": "",
    "evening_end": "",
    "slot_duration": 15,
    "days_open": [0, 1, 2, 3, 4, 5],  # Mon-Sat
    "max_patients_per_day": 0,
    "max_advance_days": 4,
    "cancel_window_hours": 1,
    "late_grace_minutes": 15,
    "languages": ["English", "Hindi", "Marathi"],
    "vaccinations_available": True,
    "teleconsult_available": False,
    "walkins_allowed": True,
    "services": ["Child Healthcare", "Vaccinations", "Growth & Development Monitoring", "Pediatric Consultations"],
}

# ---------------- Helpers ----------------
def now_utc():
    return datetime.now(timezone.utc)

def make_token(sub: str, role: str, hours: float):
    exp = now_utc() + timedelta(hours=hours)
    payload = {"sub": sub, "role": role, "iat": int(now_utc().timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG), int(exp.timestamp())

bearer = HTTPBearer(auto_error=False)

def decode_token(credentials: Optional[HTTPAuthorizationCredentials]):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Missing token")
    try:
        return jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except InvalidTokenError:
        raise HTTPException(401, "Invalid token")

def require_patient(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    p = decode_token(creds)
    if p.get("role") != "patient":
        raise HTTPException(403, "Patient access only")
    return p

def require_doctor(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    p = decode_token(creds)
    if p.get("role") != "doctor":
        raise HTTPException(403, "Doctor access only")
    return p

def require_any(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    return decode_token(creds)

def optional_doctor(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    if creds is None:
        return None
    try:
        p = decode_token(creds)
        return p if p.get("role") == "doctor" else None
    except HTTPException:
        return None

def normalize_phone(p: str) -> str:
    p = (p or "").strip().replace(" ", "").replace("-", "")
    if p.startswith("+"):
        return p
    if len(p) == 10:
        return "+91" + p
    return p

def mask_phone(p: str) -> str:
    if not p or len(p) < 5:
        return p
    return p[:5] + "X" * (len(p) - 5)

async def get_clinic():
    c = await db.clinics.find_one({"id": "default"}, {"_id": 0})
    if not c:
        await db.clinics.insert_one(DEFAULT_CLINIC.copy())
        return DEFAULT_CLINIC.copy()
    return c

def slot_list(clinic) -> List[str]:
    slots = []
    def fill(start, end):
        if not start or not end:
            return
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        cur = sh * 60 + sm
        end_min = eh * 60 + em
        while cur < end_min:
            slots.append(f"{cur//60:02d}:{cur%60:02d}")
            cur += clinic["slot_duration"]
    fill(clinic.get("morning_start", ""), clinic.get("morning_end", ""))
    fill(clinic.get("evening_start", ""), clinic.get("evening_end", ""))
    return slots

async def send_sms(phone: str, msg: str) -> bool:
    if not voicelink_client or not VOICELINK_PHONE_NUMBER:
        return False
    try:
        voicelink_client.messages.create(body=msg, from_=TWILIO_PHONE_NUMBER, to=normalize_phone(phone))
        return True
    except Exception as e:
        logger.error(f"SMS failed: {e}")
        return False

SAMPLE_RECORDINGS = [
    {
        "id": "rec-001",
        "caller_phone": "+919876543210",
        "caller_name": "Priya Sharma",
        "url": "https://download.samplelib.com/mp3/sample-12s.mp3",
        "duration_seconds": 12,
        "recorded_at_offset_days": 0,
        "transcript_preview": "Hello, I would like to book an appointment for my child for tomorrow morning.",
        "appointment_booked": True,
    },
    {
        "id": "rec-002",
        "caller_phone": "+919812345678",
        "caller_name": "Rohit Patel",
        "url": "https://download.samplelib.com/mp3/sample-9s.mp3",
        "duration_seconds": 9,
        "recorded_at_offset_days": 0,
        "transcript_preview": "Doctor available 11 to 2. Please reschedule for Saturday.",
        "appointment_booked": False,
    },
    {
        "id": "rec-003",
        "caller_phone": "+919900112233",
        "caller_name": "Anjali Verma",
        "url": "https://download.samplelib.com/mp3/sample-15s.mp3",
        "duration_seconds": 15,
        "recorded_at_offset_days": 1,
        "transcript_preview": "My baby has fever since morning. Need appointment today.",
        "appointment_booked": True,
    },
    {
        "id": "rec-004",
        "caller_phone": "+918888777666",
        "caller_name": "Unknown",
        "url": "https://download.samplelib.com/mp3/sample-6s.mp3",
        "duration_seconds": 6,
        "recorded_at_offset_days": 2,
        "transcript_preview": "Missed call. No response.",
        "appointment_booked": False,
    },
    {
        "id": "rec-005",
        "caller_phone": "+919966554433",
        "caller_name": "Kavita Iyer",
        "url": "https://download.samplelib.com/mp3/sample-3s.mp3",
        "duration_seconds": 3,
        "recorded_at_offset_days": 3,
        "transcript_preview": "Quick confirmation about Saturday slot.",
        "appointment_booked": True,
    },
]

# ---------------- Seed doctor ----------------
@app.on_event("startup")
async def seed():
    # Migrate existing clinic to new config (Phase A rename + new fields)
    existing_clinic = await db.clinics.find_one({"id": "default"})
    if existing_clinic is None:
        await db.clinics.insert_one(DEFAULT_CLINIC.copy())
    else:
        # Force-update branding + ensure new keys exist (preserves admin edits to hours/days/etc.)
        await db.clinics.update_one(
            {"id": "default"},
            {"$set": {
                "name": DEFAULT_CLINIC["name"],
                "doctor_name": DEFAULT_CLINIC["doctor_name"],
                "specialization": DEFAULT_CLINIC["specialization"],
                "qualifications": DEFAULT_CLINIC["qualifications"],
                "experience_years": DEFAULT_CLINIC["experience_years"],
                "emergency_phone": DEFAULT_CLINIC["emergency_phone"],
                "consultation_fee": existing_clinic.get("consultation_fee", DEFAULT_CLINIC["consultation_fee"]),
                "max_advance_days": existing_clinic.get("max_advance_days", DEFAULT_CLINIC["max_advance_days"]),
                "cancel_window_hours": existing_clinic.get("cancel_window_hours", DEFAULT_CLINIC["cancel_window_hours"]),
                "late_grace_minutes": existing_clinic.get("late_grace_minutes", DEFAULT_CLINIC["late_grace_minutes"]),
                "vaccinations_available": existing_clinic.get("vaccinations_available", DEFAULT_CLINIC["vaccinations_available"]),
                "teleconsult_available": existing_clinic.get("teleconsult_available", DEFAULT_CLINIC["teleconsult_available"]),
                "walkins_allowed": existing_clinic.get("walkins_allowed", DEFAULT_CLINIC["walkins_allowed"]),
                "languages": existing_clinic.get("languages", DEFAULT_CLINIC["languages"]),
                "services": DEFAULT_CLINIC["services"],
            }},
        )
    await get_clinic()
    existing = await db.doctors.find_one({"email": DOCTOR_EMAIL})
    if not existing:
        pwd_hash = bcrypt.hashpw(DOCTOR_DEFAULT_PASSWORD.encode(), bcrypt.gensalt()).decode()
        await db.doctors.insert_one({
            "id": str(uuid.uuid4()),
            "email": DOCTOR_EMAIL,
            "password_hash": pwd_hash,
            "must_change_password": True,
            "failed_attempts": 0,
            "locked_until": None,
            "created_at": now_utc().isoformat(),
        })
        logger.info(f"Seeded doctor: {DOCTOR_EMAIL}")
    # Seed sample recordings (so doctor sees real playable audio for demo IVR calls)
    if await db.recordings.count_documents({}) == 0:
        for r in SAMPLE_RECORDINGS:
            obj = {
                "id": r["id"],
                "caller_phone": r["caller_phone"],
                "caller_phone_masked": mask_phone(r["caller_phone"]),
                "caller_name": r["caller_name"],
                "url": r["url"],
                "duration_seconds": r["duration_seconds"],
                "transcript_preview": r["transcript_preview"],
                "appointment_booked": r["appointment_booked"],
                "recorded_at": (now_utc() - timedelta(days=r["recorded_at_offset_days"], hours=random.randint(1, 8))).isoformat(),
            }
            await db.recordings.insert_one(obj.copy())
        logger.info("Seeded sample recordings")
    # Create TTL index on recordings (90 days) - safe to call repeatedly
    try:
        await db.recordings.create_index("recorded_at", expireAfterSeconds=90 * 24 * 3600)
    except Exception as e:
        logger.warning(f"TTL index on recordings failed (already exists?): {e}")

# ---------------- Models ----------------
class SendOtp(BaseModel):
    phone: str

class VerifyOtp(BaseModel):
    phone: str
    otp: str

class DoctorLogin(BaseModel):
    email: str
    password: str

class ChangePassword(BaseModel):
    new_password: str

class AppointmentCreate(BaseModel):
    patient_name: str
    patient_phone: Optional[str] = None
    problem: str
    date: str
    time: str
    source: Literal["app", "ivr"] = "app"
    # Pediatric extras (optional for backward compat with patient app)
    child_name: Optional[str] = None
    child_age: Optional[str] = None
    parent_name: Optional[str] = None

class AppointmentReschedule(BaseModel):
    date: str
    time: str

class CancelAppointment(BaseModel):
    reason: Optional[str] = ""

class ClinicUpdate(BaseModel):
    name: Optional[str] = None
    doctor_name: Optional[str] = None
    specialization: Optional[str] = None
    qualifications: Optional[str] = None
    experience_years: Optional[int] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    emergency_phone: Optional[str] = None
    consultation_fee: Optional[int] = None
    morning_start: Optional[str] = None
    morning_end: Optional[str] = None
    evening_start: Optional[str] = None
    evening_end: Optional[str] = None
    slot_duration: Optional[int] = None
    days_open: Optional[List[int]] = None
    max_patients_per_day: Optional[int] = None
    max_advance_days: Optional[int] = None
    cancel_window_hours: Optional[int] = None
    late_grace_minutes: Optional[int] = None
    vaccinations_available: Optional[bool] = None
    teleconsult_available: Optional[bool] = None
    walkins_allowed: Optional[bool] = None

class BlockedDateCreate(BaseModel):
    date: str
    reason: Optional[str] = ""

class UpdateProfile(BaseModel):
    name: str

# ---------------- Auth endpoints ----------------
@api_router.post("/auth/send-otp")
async def send_otp(req: SendOtp):
    phone = normalize_phone(req.phone)
    if not phone.startswith("+") or len(phone) < 10:
        raise HTTPException(400, "Invalid phone")
    otp = f"{random.randint(0, 999999):06d}"
    await db.otps.update_one(
        {"phone": phone},
        {"$set": {"phone": phone, "otp": otp, "expires_at": (now_utc() + timedelta(minutes=5)).isoformat(), "attempts": 0}},
        upsert=True,
    )
    sent = await send_sms(phone, f"Little Stars Maternity Clinic OTP: {otp}. Valid 5 min.")
    resp = {"sent": sent, "phone": phone}
    if OTP_DEV_MODE:
        resp["dev_otp"] = otp  # For testing only
    return resp

@api_router.post("/auth/verify-otp")
async def verify_otp(req: VerifyOtp):
    phone = normalize_phone(req.phone)
    rec = await db.otps.find_one({"phone": phone})
    if not rec:
        raise HTTPException(400, "OTP not requested")
    if rec.get("attempts", 0) >= 5:
        raise HTTPException(429, "Too many attempts")
    if datetime.fromisoformat(rec["expires_at"]) < now_utc():
        raise HTTPException(400, "OTP expired")
    if rec["otp"] != req.otp:
        await db.otps.update_one({"phone": phone}, {"$inc": {"attempts": 1}})
        raise HTTPException(400, "Invalid OTP")
    await db.otps.delete_one({"phone": phone})
    # Upsert patient
    existing = await db.patients.find_one({"phone": phone}, {"_id": 0})
    if not existing:
        patient = {"id": str(uuid.uuid4()), "phone": phone, "name": "", "total_visits": 0,
                   "first_visit_date": None, "last_visit_date": None,
                   "created_at": now_utc().isoformat()}
        await db.patients.insert_one(patient.copy())
        existing = patient
    token, exp = make_token(phone, "patient", 24 * 30)  # 30 days
    return {"access_token": token, "expires_at": exp, "patient": {"id": existing["id"], "phone": phone, "name": existing.get("name", ""), "phone_masked": mask_phone(phone)}}

@api_router.post("/auth/doctor-login")
async def doctor_login(req: DoctorLogin):
    doc = await db.doctors.find_one({"email": req.email.lower().strip()})
    if not doc:
        raise HTTPException(401, "Invalid credentials")
    if doc.get("locked_until"):
        locked = datetime.fromisoformat(doc["locked_until"])
        if locked > now_utc():
            mins = int((locked - now_utc()).total_seconds() / 60) + 1
            raise HTTPException(423, f"Account locked. Try in {mins} min.")
    if not bcrypt.checkpw(req.password.encode(), doc["password_hash"].encode()):
        attempts = doc.get("failed_attempts", 0) + 1
        upd = {"failed_attempts": attempts}
        if attempts >= 5:
            upd["locked_until"] = (now_utc() + timedelta(minutes=30)).isoformat()
            upd["failed_attempts"] = 0
        await db.doctors.update_one({"email": doc["email"]}, {"$set": upd})
        raise HTTPException(401, "Invalid credentials")
    await db.doctors.update_one({"email": doc["email"]}, {"$set": {"failed_attempts": 0, "locked_until": None}})
    token, exp = make_token(doc["email"], "doctor", 0.5)  # 30 min
    return {"access_token": token, "expires_at": exp, "must_change_password": doc.get("must_change_password", False), "email": doc["email"]}

@api_router.post("/auth/doctor-change-password")
async def doctor_change_password(req: ChangePassword, doctor: dict = Depends(require_doctor)):
    pw = req.new_password
    if len(pw) < 8 or not any(c.isdigit() for c in pw) or not any(c.isalpha() for c in pw):
        raise HTTPException(400, "Password must be 8+ chars with letters and numbers")
    pwd_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()
    await db.doctors.update_one({"email": doctor["sub"]}, {"$set": {"password_hash": pwd_hash, "must_change_password": False}})
    token, exp = make_token(doctor["sub"], "doctor", 0.5)
    return {"success": True, "access_token": token, "expires_at": exp}

@api_router.post("/auth/refresh")
async def refresh(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    """Issue fresh JWT (used to reset the 30-min idle timer on activity)."""
    p = decode_token(creds)
    hours = 0.5 if p["role"] == "doctor" else 24 * 30
    token, exp = make_token(p["sub"], p["role"], hours)
    return {"access_token": token, "expires_at": exp}

# ---------------- Clinic ----------------
@api_router.get("/clinic")
async def get_clinic_info():
    c = await get_clinic()
    return c

@api_router.put("/clinic")
async def update_clinic(upd: ClinicUpdate, doctor: dict = Depends(require_doctor)):
    c = await get_clinic()
    changes = {k: v for k, v in upd.dict().items() if v is not None}
    if changes:
        await db.clinics.update_one({"id": "default"}, {"$set": changes})
    return await get_clinic()

# ---------------- Slots ----------------
@api_router.get("/slots")
async def get_slots(date: str):
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    c = await get_clinic()
    if d.weekday() not in c.get("days_open", [0, 1, 2, 3, 4, 5]):
        return {"date": date, "closed": True, "reason": "Clinic closed on this day", "slots": []}
    blocked = await db.blocked_dates.find_one({"date": date})
    if blocked:
        return {"date": date, "closed": True, "reason": blocked.get("reason") or "Holiday", "slots": []}
    booked_cursor = db.appointments.find({"date": date, "status": "confirmed"}, {"_id": 0, "time": 1})
    booked = {a["time"] async for a in booked_cursor}
    slots = [{"time": t, "available": t not in booked} for t in slot_list(c)]
    return {"date": date, "closed": False, "slots": slots}

@api_router.get("/slots/next")
async def next_slots(date: str, time: str, count: int = 3):
    """Return up to `count` next available slots starting after the given date/time."""
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    c = await get_clinic()
    all_slots = slot_list(c)
    result = []
    for delta in range(0, 21):
        cur = d + timedelta(days=delta)
        if cur.weekday() not in c.get("days_open", [0,1,2,3,4,5]):
            continue
        cur_str = cur.strftime("%Y-%m-%d")
        if await db.blocked_dates.find_one({"date": cur_str}):
            continue
        booked_cursor = db.appointments.find({"date": cur_str, "status": "confirmed"}, {"_id": 0, "time": 1})
        booked = {a["time"] async for a in booked_cursor}
        for t in all_slots:
            if delta == 0 and t <= time:
                continue
            if t not in booked:
                result.append({"date": cur_str, "time": t})
                if len(result) >= count:
                    return {"slots": result}
    return {"slots": result}

# ---------------- Appointments ----------------
async def _create_appointment(payload: AppointmentCreate, actor_role: str, actor_phone: Optional[str]):
    c = await get_clinic()
    try:
        d = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date format")
    # Max advance booking window (e.g., 4 days)
    max_days = int(c.get("max_advance_days", 4))
    today = now_utc().date()
    if d < today:
        raise HTTPException(400, "Cannot book in the past")
    if (d - today).days > max_days:
        raise HTTPException(400, f"Appointments only up to {max_days} days in advance")
    if d.weekday() not in c.get("days_open", [0,1,2,3,4,5]):
        raise HTTPException(400, "Clinic closed on this day")
    if payload.time not in slot_list(c):
        raise HTTPException(400, "Invalid time slot")
    if await db.blocked_dates.find_one({"date": payload.date}):
        raise HTTPException(400, "Date blocked")
    # Patient: phone must be from their token. Doctor (IVR): phone from payload.
    if actor_role == "patient":
        phone = actor_phone
    else:
        phone = normalize_phone(payload.patient_phone or "")
    if not phone:
        raise HTTPException(400, "Missing patient phone")
    # Patient max 2 future appointments
    if actor_role == "patient":
        tstr = today.isoformat()
        count = await db.appointments.count_documents({"patient_phone": phone, "status": "confirmed", "date": {"$gte": tstr}})
        if count >= 2:
            raise HTTPException(400, "Maximum 2 future appointments allowed")
    # Double-booking check (atomic-ish)
    existing = await db.appointments.find_one({"date": payload.date, "time": payload.time, "status": "confirmed"})
    if existing:
        nxt = await next_slots(payload.date, payload.time, 3)
        raise HTTPException(409, {"message": "Slot not available", "suggestions": nxt["slots"]})
    appt = {
        "id": str(uuid.uuid4()),
        "clinic_id": "default",
        "patient_name": payload.patient_name.strip(),
        "patient_phone": phone,
        "problem": payload.problem.strip(),
        "date": payload.date,
        "time": payload.time,
        "status": "confirmed",
        "source": payload.source,
        "child_name": (payload.child_name or "").strip() or None,
        "child_age": (payload.child_age or "").strip() or None,
        "parent_name": (payload.parent_name or payload.patient_name).strip(),
        "fee": c.get("consultation_fee", 400),
        "created_at": now_utc().isoformat(),
        "cancelled_at": None,
        "cancellation_reason": None,
    }
    await db.appointments.insert_one(appt.copy())
    # Update / upsert patient record
    await db.patients.update_one(
        {"phone": phone},
        {"$set": {"name": appt["patient_name"], "last_visit_date": appt["date"]},
         "$setOnInsert": {"id": str(uuid.uuid4()), "phone": phone, "first_visit_date": appt["date"], "total_visits": 0, "created_at": now_utc().isoformat()}},
        upsert=True,
    )
    # SMS
    msg = f"Little Stars Child Clinic\nAppointment confirmed.\nDate: {appt['date']}\nTime: {appt['time']}\nDr. {c.get('doctor_name','Bhupendra Asudani')}\nFee: \u20b9{appt['fee']}"
    await send_sms(phone, msg)
    return appt

@api_router.post("/appointments")
async def book_appointment(payload: AppointmentCreate, doctor: Optional[dict] = Depends(optional_doctor), creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
    # IVR booking requires doctor
    if payload.source == "ivr":
        if not doctor:
            raise HTTPException(401, "Doctor token required for IVR")
        return await _create_appointment(payload, "doctor", None)
    # App booking requires patient
    p = decode_token(creds)
    if p.get("role") != "patient":
        raise HTTPException(403, "Patient token required")
    return await _create_appointment(payload, "patient", p["sub"])

@api_router.get("/appointments/my")
async def my_appointments(patient: dict = Depends(require_patient)):
    today = now_utc().date().isoformat()
    docs = await db.appointments.find({"patient_phone": patient["sub"]}, {"_id": 0}).sort([("date", -1), ("time", -1)]).to_list(500)
    upcoming = [a for a in docs if a["status"] == "confirmed" and a["date"] >= today]
    past = [a for a in docs if not (a["status"] == "confirmed" and a["date"] >= today)]
    upcoming.sort(key=lambda x: (x["date"], x["time"]))
    return {"upcoming": upcoming, "past": past}

@api_router.get("/appointments/all")
async def all_appointments(scope: str = "today", doctor: dict = Depends(require_doctor)):
    today = now_utc().date()
    if scope == "today":
        q = {"date": today.isoformat()}
    elif scope == "tomorrow":
        q = {"date": (today + timedelta(days=1)).isoformat()}
    elif scope == "week":
        q = {"date": {"$gte": today.isoformat(), "$lte": (today + timedelta(days=7)).isoformat()}}
    else:
        q = {}
    docs = await db.appointments.find(q, {"_id": 0}).sort([("date", 1), ("time", 1)]).to_list(2000)
    # Mask phone for doctor view too (per spec)
    for d in docs:
        d["patient_phone_masked"] = mask_phone(d["patient_phone"])
    return docs

@api_router.put("/appointments/{appt_id}")
async def reschedule(appt_id: str, payload: AppointmentReschedule, user: dict = Depends(require_any)):
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(404, "Not found")
    if user["role"] == "patient" and appt["patient_phone"] != user["sub"]:
        raise HTTPException(403, "Not your appointment")
    if appt["status"] != "confirmed":
        raise HTTPException(400, "Cannot reschedule")
    # Check cancel/reschedule window (configurable, default 1hr)
    if user["role"] == "patient":
        c = await get_clinic()
        win = int(c.get("cancel_window_hours", 1))
        appt_dt = datetime.fromisoformat(f"{appt['date']}T{appt['time']}:00")
        if appt_dt - datetime.now() < timedelta(hours=win):
            raise HTTPException(400, f"Cannot reschedule within {win} hour(s) of appointment")
    # Validate new slot
    c = await get_clinic()
    if payload.time not in slot_list(c):
        raise HTTPException(400, "Invalid time")
    existing = await db.appointments.find_one({"date": payload.date, "time": payload.time, "status": "confirmed", "id": {"$ne": appt_id}})
    if existing:
        raise HTTPException(409, "Slot not available")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"date": payload.date, "time": payload.time}})
    return {"success": True}

@api_router.delete("/appointments/{appt_id}")
async def cancel(appt_id: str, reason: str = "", user: dict = Depends(require_any)):
    appt = await db.appointments.find_one({"id": appt_id}, {"_id": 0})
    if not appt:
        raise HTTPException(404, "Not found")
    if user["role"] == "patient" and appt["patient_phone"] != user["sub"]:
        raise HTTPException(403, "Not your appointment")
    if appt["status"] != "confirmed":
        raise HTTPException(400, "Already cancelled or completed")
    if user["role"] == "patient":
        c = await get_clinic()
        win = int(c.get("cancel_window_hours", 1))
        appt_dt = datetime.fromisoformat(f"{appt['date']}T{appt['time']}:00")
        if appt_dt - datetime.now() < timedelta(hours=win):
            raise HTTPException(400, f"Cannot cancel within {win} hour(s)")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "cancelled", "cancelled_at": now_utc().isoformat(), "cancellation_reason": reason}})
    return {"success": True}

@api_router.patch("/appointments/{appt_id}/done")
async def mark_done(appt_id: str, doctor: dict = Depends(require_doctor)):
    appt = await db.appointments.find_one({"id": appt_id})
    if not appt:
        raise HTTPException(404, "Not found")
    await db.appointments.update_one({"id": appt_id}, {"$set": {"status": "completed"}})
    await db.patients.update_one({"phone": appt["patient_phone"]}, {"$inc": {"total_visits": 1}, "$set": {"last_visit_date": appt["date"]}})
    return {"success": True}

# ---------------- Blocked dates ----------------
@api_router.get("/blocked-dates")
async def list_blocked():
    docs = await db.blocked_dates.find({}, {"_id": 0}).sort("date", 1).to_list(500)
    return docs

@api_router.post("/blocked-dates")
async def add_blocked(payload: BlockedDateCreate, doctor: dict = Depends(require_doctor)):
    try:
        datetime.strptime(payload.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date")
    existing = await db.blocked_dates.find_one({"date": payload.date})
    if existing:
        raise HTTPException(409, "Already blocked")
    obj = {"id": str(uuid.uuid4()), "date": payload.date, "reason": payload.reason or "", "created_at": now_utc().isoformat()}
    await db.blocked_dates.insert_one(obj.copy())
    return obj

@api_router.delete("/blocked-dates/{date_str}")
async def del_blocked(date_str: str, doctor: dict = Depends(require_doctor)):
    res = await db.blocked_dates.delete_one({"date": date_str})
    if res.deleted_count == 0:
        raise HTTPException(404, "Not blocked")
    return {"success": True}

# ---------------- Patient profile ----------------
@api_router.get("/patient/me")
async def get_me(patient: dict = Depends(require_patient)):
    p = await db.patients.find_one({"phone": patient["sub"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Not found")
    total = await db.appointments.count_documents({"patient_phone": patient["sub"]})
    p["total_visits"] = total
    p["phone_masked"] = mask_phone(p["phone"])
    return p

@api_router.put("/patient/me")
async def update_me(payload: UpdateProfile, patient: dict = Depends(require_patient)):
    await db.patients.update_one({"phone": patient["sub"]}, {"$set": {"name": payload.name.strip()}})
    return {"success": True}

@api_router.delete("/patient/me")
async def delete_me(patient: dict = Depends(require_patient)):
    await db.appointments.delete_many({"patient_phone": patient["sub"]})
    await db.patients.delete_one({"phone": patient["sub"]})
    return {"success": True}

# ---------------- Doctor overview & analytics ----------------
# ---------------- Doctor overview & analytics ----------------
@api_router.get("/doctor/overview")
async def overview(doctor: dict = Depends(require_doctor)):
    today = now_utc().date().isoformat()
    total_today = await db.appointments.count_documents({"date": today, "status": {"$in": ["confirmed", "completed"]}})
    completed = await db.appointments.count_documents({"date": today, "status": "completed"})
    via_app = await db.appointments.count_documents({"date": today, "source": "app", "status": {"$ne": "cancelled"}})
    via_ivr = await db.appointments.count_documents({"date": today, "source": "ivr", "status": {"$ne": "cancelled"}})
    return {"date": today, "total_today": total_today, "completed": completed, "via_app": via_app, "via_phone": via_ivr}

@api_router.get("/doctor/analytics")
async def analytics(doctor: dict = Depends(require_doctor)):
    today = now_utc().date()
    month_start = today.replace(day=1).isoformat()
    month_q = {"date": {"$gte": month_start}}
    month_total = await db.appointments.count_documents(month_q)
    month_app = await db.appointments.count_documents({**month_q, "source": "app"})
    month_ivr = await db.appointments.count_documents({**month_q, "source": "ivr"})
    month_cancelled = await db.appointments.count_documents({**month_q, "status": "cancelled"})
    month_completed = await db.appointments.count_documents({**month_q, "status": "completed"})
    
    # Busiest day of week + busiest time
    docs = await db.appointments.find(month_q, {"_id": 0, "date": 1, "time": 1, "patient_phone": 1, "status": 1}).to_list(5000)
    by_dow = [0] * 7
    by_hour = {}
    phone_count = {}
    
    for a in docs:
        try:
            dt = datetime.strptime(a["date"], "%Y-%m-%d")
            by_dow[dt.weekday()] += 1
        except Exception:
            pass
        h = a.get("time", "00:00").split(":")[0]
        by_hour[h] = by_hour.get(h, 0) + 1
        
        if "patient_phone" in a:
            phone_count[a["patient_phone"]] = phone_count.get(a["patient_phone"], 0) + 1
            
    returning = sum(1 for v in phone_count.values() if v > 1)
    new_p = sum(1 for v in phone_count.values() if v == 1)
    cancellation_rate = (month_cancelled / month_total * 100) if month_total else 0
    no_show_rate = 0  
    
    return {
        "month_total": month_total,
        "month_app": month_app,
        "month_ivr": month_ivr,
        "month_completed": month_completed,
        "month_cancelled": month_cancelled,
        "cancellation_rate": round(cancellation_rate, 1),
        "no_show_rate": no_show_rate,
        "by_dow": by_dow,  
        "by_hour": [{"hour": k, "count": v} for k, v in sorted(by_hour.items())],
        "new_patients": new_p,
        "returning_patients": returning,
    }

# ---------------- Recordings ----------------
@api_router.get("/recordings")
async def list_recordings(doctor: dict = Depends(require_doctor)):
    docs = await db.recordings.find({}, {"_id": 0}).sort("recorded_at", -1).to_list(500)
    return {"recordings": docs}

class RecordingCreate(BaseModel):
    caller_phone: str
    caller_name: Optional[str] = "Unknown"
    url: str
    duration_seconds: int = 0
    transcript_preview: Optional[str] = ""
    appointment_booked: bool = False

@api_router.post("/recordings")
async def add_recording(payload: RecordingCreate, doctor: dict = Depends(require_doctor)):
    obj = {
        "id": str(uuid.uuid4()),
        "caller_phone": normalize_phone(payload.caller_phone),
        "caller_phone_masked": mask_phone(normalize_phone(payload.caller_phone)),
        "caller_name": payload.caller_name or "Unknown",
        "url": payload.url,
        "duration_seconds": int(payload.duration_seconds or 0),
        "transcript_preview": payload.transcript_preview or "",
        "appointment_booked": bool(payload.appointment_booked),
        "recorded_at": now_utc().isoformat(),
    }
    await db.recordings.insert_one(obj.copy())
    return obj

@api_router.delete("/recordings/{rec_id}")
async def delete_recording(rec_id: str, doctor: dict = Depends(require_doctor)):
    res = await db.recordings.delete_one({"id": rec_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Not found")
    return {"success": True}

# ---------------- Waitlist ----------------
class WaitlistCreate(BaseModel):
    parent_name: str
    parent_phone: str
    child_name: Optional[str] = ""
    child_age: Optional[str] = ""
    preferred_date: str
    problem: Optional[str] = ""
    source: Literal["app", "ivr"] = "app"

@api_router.get("/waitlist")
async def list_waitlist(doctor: dict = Depends(require_doctor)):
    docs = await db.waitlist.find({"status": "waiting"}, {"_id": 0}).sort("created_at", 1).to_list(500)
    for d in docs:
        d["parent_phone_masked"] = mask_phone(d.get("parent_phone", ""))
    return docs

@api_router.post("/waitlist")
async def add_waitlist(payload: WaitlistCreate, doctor: Optional[dict] = Depends(optional_doctor)):
    phone = normalize_phone(payload.parent_phone)
    obj = {
        "id": str(uuid.uuid4()),
        "parent_name": payload.parent_name.strip(),
        "parent_phone": phone,
        "child_name": (payload.child_name or "").strip(),
        "child_age": (payload.child_age or "").strip(),
        "preferred_date": payload.preferred_date,
        "problem": (payload.problem or "").strip(),
        "source": payload.source,
        "status": "waiting",
        "created_at": now_utc().isoformat(),
    }
    await db.waitlist.insert_one(obj.copy())
    return obj

@api_router.delete("/waitlist/{wid}")
async def remove_waitlist(wid: str, doctor: dict = Depends(require_doctor)):
    res = await db.waitlist.update_one({"id": wid}, {"$set": {"status": "removed", "removed_at": now_utc().isoformat()}})
    if res.modified_count == 0:
        raise HTTPException(404, "Not found")
    return {"success": True}

# ---------------- IVR webhooks (no JWT, shared secret) ----------------
def require_ivr(x_ivr_secret: str = Header(default="")):
    if not x_ivr_secret or x_ivr_secret != IVR_SECRET:
        raise HTTPException(401, "Invalid IVR secret")
    return True

class IvrCheck(BaseModel):
    date: str
    time: Optional[str] = None

class IvrBook(BaseModel):
    parent_name: str
    parent_phone: str
    child_name: str
    child_age: str
    problem: str
    date: str
    time: str

class IvrCancel(BaseModel):
    parent_phone: str
    date: str
    time: str

class IvrRecording(BaseModel):
    call_id: str
    caller_phone: str
    caller_name: Optional[str] = "Unknown"
    url: str
    duration_seconds: int = 0
    transcript_preview: Optional[str] = ""
    appointment_booked: bool = False

@api_router.post("/ivr/check-availability")
async def ivr_check(req: IvrCheck, ok: bool = Depends(require_ivr)):
    c = await get_clinic()
    try:
        d = datetime.strptime(req.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Invalid date")
    if d.weekday() not in c.get("days_open", [0,1,2,3,4,5]):
        return {"available": False, "reason": "Clinic closed on this day", "next_slots": (await next_slots(req.date, req.time or "00:00", 3))["slots"]}
    if await db.blocked_dates.find_one({"date": req.date}):
        return {"available": False, "reason": "Holiday", "next_slots": (await next_slots(req.date, req.time or "00:00", 3))["slots"]}
    if req.time:
        existing = await db.appointments.find_one({"date": req.date, "time": req.time, "status": "confirmed"})
        if existing:
            return {"available": False, "reason": "Slot taken", "next_slots": (await next_slots(req.date, req.time, 3))["slots"]}
        return {"available": True, "date": req.date, "time": req.time, "fee": c.get("consultation_fee", 400)}
    booked_cursor = db.appointments.find({"date": req.date, "status": "confirmed"}, {"_id": 0, "time": 1})
    booked = {a["time"] async for a in booked_cursor}
    free = [t for t in slot_list(c) if t not in booked]
    return {"available": len(free) > 0, "free_slots": free, "fee": c.get("consultation_fee", 400)}

@api_router.post("/ivr/book")
async def ivr_book(req: IvrBook, ok: bool = Depends(require_ivr)):
    payload = AppointmentCreate(
        patient_name=req.parent_name,
        patient_phone=req.parent_phone,
        problem=req.problem,
        date=req.date,
        time=req.time,
        source="ivr",
        child_name=req.child_name,
        child_age=req.child_age,
        parent_name=req.parent_name,
    )
    appt = await _create_appointment(payload, "ivr", None)
    return {"success": True, "appointment_id": appt["id"], "fee": appt.get("fee", 400)}

@api_router.post("/ivr/cancel")
async def ivr_cancel(req: IvrCancel, ok: bool = Depends(require_ivr)):
    phone = normalize_phone(req.parent_phone)
    appt = await db.appointments.find_one({"patient_phone": phone, "date": req.date, "time": req.time, "status": "confirmed"})
    if not appt:
        raise HTTPException(404, "No matching appointment")
    await db.appointments.update_one({"id": appt["id"]}, {"$set": {"status": "cancelled", "cancelled_at": now_utc().isoformat(), "cancellation_reason": "Cancelled via IVR"}})
    return {"success": True}

@api_router.post("/ivr/waitlist")
async def ivr_waitlist(req: WaitlistCreate, ok: bool = Depends(require_ivr)):
    req.source = "ivr"
    phone = normalize_phone(req.parent_phone)
    obj = {
        "id": str(uuid.uuid4()),
        "parent_name": req.parent_name.strip(),
        "parent_phone": phone,
        "child_name": (req.child_name or "").strip(),
        "child_age": (req.child_age or "").strip(),
        "preferred_date": req.preferred_date,
        "problem": (req.problem or "").strip(),
        "source": "ivr",
        "status": "waiting",
        "created_at": now_utc().isoformat(),
    }
    await db.waitlist.insert_one(obj.copy())
    return {"success": True, "id": obj["id"]}

@api_router.post("/ivr/recordings")
async def ivr_save_recording(req: IvrRecording, ok: bool = Depends(require_ivr)):
    phone = normalize_phone(req.caller_phone)
    obj = {
        "id": req.call_id or str(uuid.uuid4()),
        "caller_phone": phone,
        "caller_phone_masked": mask_phone(phone),
        "caller_name": req.caller_name or "Unknown",
        "url": req.url,
        "duration_seconds": int(req.duration_seconds or 0),
        "transcript_preview": req.transcript_preview or "",
        "appointment_booked": bool(req.appointment_booked),
        "recorded_at": now_utc().isoformat(),
    }
    await db.recordings.insert_one(obj.copy())
    return {"success": True, "id": obj["id"]}

# ---------------- Health ----------------
@api_router.get("/")
async def root():
    return {"status": "success", "message": "ClinicBot AI Backend is active and connected to MongoDB!"}

app.include_router(api_router)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown():
    client.close()
