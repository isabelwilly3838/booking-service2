from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)
    full_name: str
    role: Literal["patient", "doctor"]


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: str


class SlotIn(BaseModel):
    start_time: datetime
    end_time: datetime


class SlotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime


class BookIn(BaseModel):
    slot_id: int


class RescheduleIn(BaseModel):
    new_slot_id: int


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slot_id: int
    patient_id: int
    status: str