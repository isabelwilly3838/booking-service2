from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import models


def register(client, email, role, password="password123"):
    response = client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": "Test User", "role": role},
    )
    assert response.status_code == 201
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def in_hours(hours):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def make_slot(client, doctor_headers, start_hours=24):
    response = client.post(
        "/slots",
        json={"start_time": in_hours(start_hours), "end_time": in_hours(start_hours + 1)},
        headers=doctor_headers,
    )
    assert response.status_code == 201
    return response.json()


def test_duplicate_email_is_rejected(client):
    register(client, "a@example.com", "patient")
    response = client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "password123", "full_name": "A", "role": "patient"},
    )
    assert response.status_code == 409


def test_wrong_password_is_rejected(client):
    register(client, "a@example.com", "patient")
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "nope-nope"})
    assert response.status_code == 401


def test_patient_cannot_create_slot(client):
    patient = register(client, "p@example.com", "patient")
    response = client.post(
        "/slots", json={"start_time": in_hours(24), "end_time": in_hours(25)}, headers=patient
    )
    assert response.status_code == 403


def test_overlapping_slots_are_rejected(client):
    doctor = register(client, "d@example.com", "doctor")
    make_slot(client, doctor, start_hours=24)
    response = client.post(
        "/slots", json={"start_time": in_hours(24.5), "end_time": in_hours(25.5)}, headers=doctor
    )
    assert response.status_code == 409


def test_patient_can_book_a_slot(client):
    doctor = register(client, "d@example.com", "doctor")
    patient = register(client, "p@example.com", "patient")
    slot = make_slot(client, doctor)

    response = client.post("/appointments", json={"slot_id": slot["id"]}, headers=patient)

    assert response.status_code == 201
    assert response.json()["status"] == "booked"
    assert client.get("/slots").json() == []  # no longer available


def test_double_booking_is_rejected(client):
    doctor = register(client, "d@example.com", "doctor")
    first = register(client, "p1@example.com", "patient")
    second = register(client, "p2@example.com", "patient")
    slot = make_slot(client, doctor)

    client.post("/appointments", json={"slot_id": slot["id"]}, headers=first)
    response = client.post("/appointments", json={"slot_id": slot["id"]}, headers=second)

    assert response.status_code == 409


def test_booking_a_past_slot_is_rejected(client, db):
    register(client, "d@example.com", "doctor")
    patient = register(client, "p@example.com", "patient")
    doctor = db.scalar(select(models.User).where(models.User.email == "d@example.com"))
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    slot = models.Slot(doctor_id=doctor.id, start_time=past, end_time=past + timedelta(hours=1))
    db.add(slot)
    db.commit()

    response = client.post("/appointments", json={"slot_id": slot.id}, headers=patient)

    assert response.status_code == 422


def test_cancelling_frees_the_slot(client):
    doctor = register(client, "d@example.com", "doctor")
    patient = register(client, "p@example.com", "patient")
    slot = make_slot(client, doctor)
    appointment = client.post("/appointments", json={"slot_id": slot["id"]}, headers=patient).json()

    response = client.post(f"/appointments/{appointment['id']}/cancel", headers=patient)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert len(client.get("/slots").json()) == 1


def test_reschedule_moves_the_appointment(client):
    doctor = register(client, "d@example.com", "doctor")
    patient = register(client, "p@example.com", "patient")
    old_slot = make_slot(client, doctor, start_hours=24)
    new_slot = make_slot(client, doctor, start_hours=48)
    appointment = client.post("/appointments", json={"slot_id": old_slot["id"]}, headers=patient).json()

    response = client.post(
        f"/appointments/{appointment['id']}/reschedule",
        json={"new_slot_id": new_slot["id"]},
        headers=patient,
    )

    assert response.status_code == 200
    assert response.json()["slot_id"] == new_slot["id"]


def test_other_patient_cannot_cancel(client):
    doctor = register(client, "d@example.com", "doctor")
    owner = register(client, "p1@example.com", "patient")
    stranger = register(client, "p2@example.com", "patient")
    slot = make_slot(client, doctor)
    appointment = client.post("/appointments", json={"slot_id": slot["id"]}, headers=owner).json()

    response = client.post(f"/appointments/{appointment['id']}/cancel", headers=stranger)

    assert response.status_code == 403