from __future__ import annotations

import base64
import binascii
import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KpspAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    actual_age_months: int = Field(ge=0, le=72)
    birth_date: date | None = None
    screening_date: date | None = None
    screening_age_months: int
    screening_mode: Literal["routine", "concern"] = "routine"
    status: Literal["draft", "submitted"] = "submitted"
    answers: dict[int, Literal["Ya", "Tidak"]] = Field(default_factory=dict)

    @field_validator("screening_age_months")
    @classmethod
    def screening_age_is_in_schedule(cls, value: int) -> int:
        schedule = {3, 6, 9, 12, 15, 18, 21, 24, 30, 36, 42, 48, 54, 60, 66, 72}
        if value not in schedule:
            raise ValueError("Usia skrining harus mengikuti jadwal KPSP pada PDF.")
        return value


class MessaCareAnnouncementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_name: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=500)
    session: str = Field(min_length=1, max_length=30)
    time: str = Field(min_length=1, max_length=10)


class MessaCareAnnouncementResponse(BaseModel):
    text: str
    engine: str
    demo: bool = True
    generated_at: str


class MealSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    meal_id: str = Field(min_length=1, max_length=80)
    servings: float = Field(default=1.0, ge=0.25, le=5)

    @field_validator("meal_id")
    @classmethod
    def trim_selected_meal_id(cls, value: str) -> str:
        return value.strip()


class DaycareActivityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    child_name: str = Field(min_length=1, max_length=80)
    category: Literal[
        "Makan & minum", "Tidur", "Stimulasi", "Bermain", "Belajar", "Kejadian",
    ]
    title: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=1000)
    session: Literal["Pagi", "Siang", "Sore"]
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    share_to_parent: bool = False
    duration_minutes: int | None = Field(default=None, ge=1, le=720)
    mood: Literal["Senang", "Tenang", "Membutuhkan dukungan", "Belum dicatat"] | None = None
    participation: Literal["Mandiri", "Dengan dukungan", "Mengamati", "Belum dicatat"] | None = None
    water_ml: int | None = Field(default=None, ge=0, le=3000)
    meal_id: str | None = Field(default=None, max_length=80)
    meal_servings: float = Field(default=1.0, ge=0.25, le=5)
    meal_items: list[MealSelection] = Field(default_factory=list, max_length=8)
    photo_data_url: str | None = Field(default=None, max_length=2_800_000)
    photo_consent_confirmed: bool = False
    # 300 MB binary media becomes roughly 400 MB as base64 data URL.
    media_data_url: str | None = Field(default=None, max_length=420_000_000)
    media_consent_confirmed: bool = False

    @field_validator("child_name", "title", "note")
    @classmethod
    def trim_activity_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Kolom ini tidak boleh kosong.")
        return normalized

    @field_validator("meal_id")
    @classmethod
    def trim_meal_id(cls, value: str | None) -> str | None:
        return value.strip() if value and value.strip() else None

    @field_validator("photo_data_url")
    @classmethod
    def validate_photo_data_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            header, encoded = value.split(",", 1)
        except ValueError as exc:
            raise ValueError("Format foto tidak valid.") from exc
        match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64", header)
        if not match:
            raise ValueError("Foto harus berupa JPEG, PNG, atau WebP.")
        try:
            image = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("Isi foto tidak dapat dibaca.") from exc
        if not image or len(image) > 2 * 1024 * 1024:
            raise ValueError("Ukuran foto maksimal 2 MB.")
        content_type = match.group(1)
        signatures = {
            "image/jpeg": image.startswith(b"\xff\xd8\xff"),
            "image/png": image.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": len(image) >= 12 and image[:4] == b"RIFF" and image[8:12] == b"WEBP",
        }
        if not signatures[content_type]:
            raise ValueError("Jenis berkas foto tidak sesuai dengan isinya.")
        return value

    @field_validator("media_data_url")
    @classmethod
    def validate_media_data_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            header, encoded = value.split(",", 1)
            match = re.fullmatch(r"data:(image/(?:jpeg|png|webp)|video/[a-z0-9.+-]+);base64", header, re.IGNORECASE)
            if not match:
                raise ValueError("Format media tidak dikenali. Pilih foto atau berkas video yang valid.")
            media = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Berkas media tidak dapat dibaca.") from exc
        if not media or len(media) > 300 * 1024 * 1024:
            raise ValueError("Ukuran foto atau video maksimal 300 MB.")
        return value

    @model_validator(mode="after")
    def confirm_photo_privacy(self) -> "DaycareActivityCreate":
        if self.photo_data_url and not self.photo_consent_confirmed:
            raise ValueError("Konfirmasi privasi dan persetujuan diperlukan sebelum menyimpan foto.")
        if (self.meal_id or self.meal_items) and self.category != "Makan & minum":
            raise ValueError("Menu makanan hanya dapat dilampirkan pada catatan Makan & minum.")
        if self.media_data_url and not self.media_consent_confirmed:
            raise ValueError("Konfirmasi privasi media sebelum menyimpan foto atau video.")
        if self.meal_id and self.meal_items:
            raise ValueError("Gunakan pilihan menu majemuk atau menu tunggal, bukan keduanya.")
        if len({item.meal_id for item in self.meal_items}) != len(self.meal_items):
            raise ValueError("Menu yang sama tidak perlu ditambahkan dua kali; ubah jumlah porsinya.")
        return self


class MealCatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    serving_label: str = Field(min_length=2, max_length=80)
    serving_grams: float = Field(gt=0, le=5000)
    energy_kcal: float = Field(ge=0, le=10000)
    protein_g: float = Field(ge=0, le=1000)
    carbohydrate_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)
    fiber_g: float = Field(ge=0, le=1000)
    source: str = Field(default="Sumber belum dicantumkan", min_length=1, max_length=160)
    source_url: str = Field(default="", max_length=500)
    allergens: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=500)

    @field_validator("name", "serving_label", "source", "allergens", "notes")
    @classmethod
    def normalize_meal_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("source_url")
    @classmethod
    def validate_meal_source_url(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not normalized.lower().startswith(("https://", "http://")):
            raise ValueError("Tautan sumber harus menggunakan alamat http atau https.")
        return normalized

    @field_validator("name", "serving_label", "source")
    @classmethod
    def required_meal_text(cls, value: str) -> str:
        if not value:
            raise ValueError("Kolom ini tidak boleh kosong.")
        return value


class DevelopmentReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    period_start: date
    period_end: date
    summary: str = Field(min_length=1, max_length=2000)

    @field_validator("summary")
    @classmethod
    def trim_report_summary(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Ringkasan faktual tidak boleh kosong.")
        return normalized

    @model_validator(mode="after")
    def validate_period(self) -> "DevelopmentReportCreate":
        if self.period_start > self.period_end:
            raise ValueError("Tanggal awal periode harus sebelum tanggal akhir.")
        period_days = (self.period_end - self.period_start).days
        if period_days < 80 or period_days > 100:
            raise ValueError("Rentang laporan harus sekitar tiga bulan (80–100 hari).")
        return self


class MilestoneObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    aspect: Literal["Motorik kasar", "Motorik halus", "Bahasa", "Sosial-emosional"]
    milestone: str = Field(default="", max_length=240)
    reference: str = Field(default="", max_length=120)
    result: Literal["Teramati", "Belum teramati", "Belum ada kesempatan"]
    context: str = Field(min_length=1, max_length=300)
    note: str = Field(min_length=1, max_length=1000)
    time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")

    @field_validator("milestone", "reference")
    @classmethod
    def trim_observation_metadata(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("context", "note")
    @classmethod
    def trim_required_observation_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Isi konteks dan pengamatan tidak boleh kosong.")
        return normalized


class StimulationFeedbackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    activity_id: str = Field(min_length=1, max_length=100)
    outcome: Literal["tertarik", "sebagian", "menolak", "belum_dicoba"]
    duration_minutes: int | None = Field(default=None, ge=1, le=180)
    note: str = Field(default="", max_length=500)

    @field_validator("note")
    @classmethod
    def trim_feedback_note(cls, value: str) -> str:
        return " ".join(value.split())


class KpspReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal[
        "Kumpulkan observasi tambahan",
        "Berikan kegiatan stimulasi umum",
        "Jadwalkan konsultasi dengan keluarga",
        "Tidak ada tindak lanjut saat ini",
    ]
    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def trim_review_note(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Catatan dokter tidak boleh kosong.")
        return normalized


class AttendanceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    status: Literal["Hadir", "Izin", "Sakit"]


class PickupAuthorizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    relationship: str = Field(min_length=2, max_length=40)
    parent_confirmation_method: Literal["in_person", "phone", "offline_written_record"]
    parent_confirmation_recorded: bool

    @field_validator("name", "relationship")
    @classmethod
    def normalize_pickup_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Isi sedikitnya dua karakter.")
        return normalized

    @model_validator(mode="after")
    def require_parent_confirmation(self) -> "PickupAuthorizationCreate":
        if not self.parent_confirmation_recorded:
            raise ValueError("Catat penjemput hanya setelah konfirmasi orang tua/wali di luar aplikasi.")
        return self


class AttendanceCheckInCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)


class AttendanceCheckOutCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    pickup_authorization_id: str = Field(min_length=1, max_length=100)
    pickup_name_match_confirmed: bool

    @model_validator(mode="after")
    def require_in_person_match(self) -> "AttendanceCheckOutCreate":
        if not self.pickup_name_match_confirmed:
            raise ValueError("Penjemput harus dicocokkan langsung dengan daftar yang aktif.")
        return self


class FamilyMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str | None = Field(default=None, min_length=1, max_length=80)
    recipient_id: str | None = Field(default=None, min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("recipient_id")
    @classmethod
    def normalize_recipient_id(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else None
        return normalized or None

    @field_validator("text")
    @classmethod
    def trim_message_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Isi pesan tidak boleh kosong.")
        return normalized


class FamilyReminderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=1, max_length=500)
    due_at: datetime
    audience: Literal["family", "self"] = "family"

    @field_validator("title", "body")
    @classmethod
    def normalize_reminder_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Judul dan isi pengingat tidak boleh kosong.")
        return normalized

    @field_validator("due_at")
    @classmethod
    def require_timezone_for_reminder(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Waktu pengingat harus menyertakan zona waktu.")
        return value


class SensorDeviceRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=2, max_length=80)
    room_id: str = Field(min_length=1, max_length=80)

    @field_validator("device_id", "room_id")
    @classmethod
    def trim_sensor_device_fields(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Kolom ini tidak boleh kosong.")
        return normalized


class SensorReadingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_id: str = Field(min_length=1, max_length=80)
    room_id: str = Field(min_length=1, max_length=80)
    temperature_c: float = Field(ge=-10, le=60)
    humidity_pct: float = Field(ge=0, le=100)
    measured_at: datetime | None = None

    @field_validator("device_id", "room_id")
    @classmethod
    def normalize_sensor_ids(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("ID perangkat dan ruang tidak boleh kosong.")
        return normalized

    @field_validator("measured_at")
    @classmethod
    def require_timezone_for_reading(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Waktu pembacaan harus menyertakan zona waktu.")
        return value


class ChildProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    birth_date: date | None = None
    room: str = Field(default="", max_length=80)
    organization_id: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("name", "room")
    @classmethod
    def normalize_child_profile_text(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("birth_date")
    @classmethod
    def birth_date_is_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Tanggal lahir tidak boleh di masa depan.")
        return value


class ChildProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=2, max_length=80)
    birth_date: date | None = None
    room: str | None = Field(default=None, max_length=80)

    @field_validator("name")
    @classmethod
    def normalize_updated_child_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Nama profil perlu sedikitnya dua karakter.")
        return normalized

    @field_validator("room")
    @classmethod
    def normalize_updated_child_room(cls, value: str | None) -> str | None:
        return " ".join(value.split()) if value is not None else None

    @field_validator("birth_date")
    @classmethod
    def updated_birth_date_is_not_in_future(cls, value: date | None) -> date | None:
        if value is not None and value > date.today():
            raise ValueError("Tanggal lahir tidak boleh di masa depan.")
        return value

    @model_validator(mode="after")
    def require_update_field(self) -> "ChildProfileUpdate":
        if not self.model_fields_set:
            raise ValueError("Pilih setidaknya satu kolom profil untuk diperbarui.")
        if ("name" in self.model_fields_set and self.name is None) or ("room" in self.model_fields_set and self.room is None):
            raise ValueError("Nama dan ruang tidak dapat dihapus; gunakan teks kosong untuk mengosongkan ruang.")
        return self


class GuardianLinkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_user_id: str = Field(min_length=1, max_length=80)
    relationship: str = Field(min_length=2, max_length=40)
    verification_method: Literal["in_person", "document_review", "institution_record"]
    institution_check_confirmed: bool

    @field_validator("relationship")
    @classmethod
    def normalize_guardian_relationship(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 2:
            raise ValueError("Relasi wali perlu dijelaskan singkat.")
        return normalized

    @model_validator(mode="after")
    def require_institution_check(self) -> "GuardianLinkCreate":
        if not self.institution_check_confirmed:
            raise ValueError("Konfirmasi pemeriksaan relasi wali oleh institusi diperlukan.")
        return self


class GuardianLinkAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_relationship: bool

    @model_validator(mode="after")
    def require_parent_confirmation(self) -> "GuardianLinkAccept":
        if not self.confirm_relationship:
            raise ValueError("Konfirmasi wali diperlukan sebelum profil dibuka.")
        return self


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("Masukkan alamat email yang valid.")
        return normalized


class AuthRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=160)
    password: str = Field(min_length=10, max_length=200)
    # Staff accounts are invitation-managed; public self-registration is parent-only.
    role: Literal["parent"] = "parent"

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 2:
            raise ValueError("Nama perlu sedikitnya dua karakter.")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or "." not in normalized.rsplit("@", 1)[-1]:
            raise ValueError("Masukkan alamat email yang valid.")
        return normalized
