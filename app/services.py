from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def create_slot(db: Session, doctor: models.User, start: datetime, end: datetime) -> models.Slot:
    start, end = to_naive_utc(start), to_naive_utc(end)
    if end <= start:
        raise HTTPException(422, "End time must be after start time")
    if start <= utcnow():
        raise HTTPException(422, "Slot must be in the future")
    overlap = db.scalar(
        select(models.Slot).where(
            models.Slot.doctor_id == doctor.id,
            models.Slot.start_time < end,
            models.Slot.end_time > start,
        )
    )
    if overlap:
        raise HTTPException(409, "Slot overlaps an existing slot")
    slot = models.Slot(doctor_id=doctor.id, start_time=start, end_time=end)
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


def available_slots(db: Session, doctor_id: int | None = None) -> list[models.Slot]:
    booked = select(models.Appointment.slot_id).where(models.Appointment.status == "booked")
    query = (
        select(models.Slot)
        .where(models.Slot.start_time > utcnow(), models.Slot.id.not_in(booked))
        .order_by(models.Slot.start_time)
    )
    if doctor_id is not None:
        query = query.where(models.Slot.doctor_id == doctor_id)
    return list(db.scalars(query))


def _get_bookable_slot(db: Session, slot_id: int) -> models.Slot:
    slot = db.get(models.Slot, slot_id)
    if slot is None:
        raise HTTPException(404, "Slot not found")
    if slot.start_time <= utcnow():
        raise HTTPException(422, "Cannot book a slot in the past")
    already_booked = db.scalar(
        select(models.Appointment).where(
            models.Appointment.slot_id == slot_id, models.Appointment.status == "booked"
        )
    )
    if already_booked:
        raise HTTPException(409, "Slot is already booked")
    return slot


def _own_active_appointment(db: Session, patient: models.User, appointment_id: int) -> models.Appointment:
    appointment = db.get(models.Appointment, appointment_id)
    if appointment is None:
        raise HTTPException(404, "Appointment not found")
    if appointment.patient_id != patient.id:
        raise HTTPException(403, "This is not your appointment")
    if appointment.status != "booked":
        raise HTTPException(409, "Appointment is not active")
    return appointment


def book(db: Session, patient: models.User, slot_id: int) -> models.Appointment:
    _get_bookable_slot(db, slot_id)
    appointment = models.Appointment(slot_id=slot_id, patient_id=patient.id, status="booked")
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def cancel(db: Session, patient: models.User, appointment_id: int) -> models.Appointment:
    appointment = _own_active_appointment(db, patient, appointment_id)
    appointment.status = "cancelled"
    db.commit()
    db.refresh(appointment)
    return appointment


def reschedule(
    db: Session, patient: models.User, appointment_id: int, new_slot_id: int
) -> models.Appointment:
    appointment = _own_active_appointment(db, patient, appointment_id)
    _get_bookable_slot(db, new_slot_id)
    appointment.slot_id = new_slot_id
    db.commit()
    db.refresh(appointment)
    return appointment