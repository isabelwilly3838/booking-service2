from contextlib import asynccontextmanager

import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas, security, services
from app.database import Base, engine, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Booking Service", lifespan=lifespan)
bearer = HTTPBearer()


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> models.User:
    try:
        payload = security.decode_token(credentials.credentials)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token") from None
    user = db.get(models.User, int(payload["sub"]))
    if user is None:
        raise HTTPException(401, "User no longer exists")
    return user


def require_role(role: str):
    def checker(user: models.User = Depends(current_user)) -> models.User:
        if user.role != role:
            raise HTTPException(403, f"Only {role}s can do this")
        return user

    return checker


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/auth/register", response_model=schemas.UserOut, status_code=201)
def register(body: schemas.RegisterIn, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(models.User).where(models.User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = models.User(
        email=email,
        full_name=body.full_name,
        password_hash=security.hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(models.User).where(models.User.email == body.email.lower()))
    if user is None or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return schemas.TokenOut(access_token=security.create_token(user.id, user.role))


@app.post("/slots", response_model=schemas.SlotOut, status_code=201)
def create_slot(
    body: schemas.SlotIn,
    doctor: models.User = Depends(require_role("doctor")),
    db: Session = Depends(get_db),
):
    return services.create_slot(db, doctor, body.start_time, body.end_time)


@app.get("/slots", response_model=list[schemas.SlotOut])
def list_slots(doctor_id: int | None = None, db: Session = Depends(get_db)):
    return services.available_slots(db, doctor_id)


@app.post("/appointments", response_model=schemas.AppointmentOut, status_code=201)
def book_appointment(
    body: schemas.BookIn,
    patient: models.User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
):
    return services.book(db, patient, body.slot_id)


@app.get("/appointments/me", response_model=list[schemas.AppointmentOut])
def my_appointments(
    patient: models.User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
):
    return list(db.scalars(select(models.Appointment).where(models.Appointment.patient_id == patient.id)))


@app.post("/appointments/{appointment_id}/cancel", response_model=schemas.AppointmentOut)
def cancel_appointment(
    appointment_id: int,
    patient: models.User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
):
    return services.cancel(db, patient, appointment_id)


@app.post("/appointments/{appointment_id}/reschedule", response_model=schemas.AppointmentOut)
def reschedule_appointment(
    appointment_id: int,
    body: schemas.RescheduleIn,
    patient: models.User = Depends(require_role("patient")),
    db: Session = Depends(get_db),
):
    return services.reschedule(db, patient, appointment_id, body.new_slot_id)