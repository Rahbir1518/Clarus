"""Practice settings: opening hours and appointment length.

Set by the doctor in the app and kept until they change them. Read by the agent
tools during a call and by the booking step after one, so the validation here is
what keeps a malformed week from reaching a patient as "we are open from five
to nine" or an overlapping range from booking one slot twice.
"""
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.scheduling.availability import WEEKDAYS, parse_hhmm

# A day with more than this many separate opening ranges is a data-entry
# mistake, not a clinic.
MAX_RANGES_PER_DAY = 4


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: str = Field(..., description="Opening time, HH:MM (24-hour)")
    end: str = Field(..., description="Closing time, HH:MM (24-hour)")

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, value: str) -> str:
        try:
            parse_hhmm(value)
        except ValueError as exc:
            raise ValueError(f"{value!r} is not a time in HH:MM (24-hour) form") from exc
        return value

    @model_validator(mode="after")
    def _ordered(self) -> "TimeRange":
        if parse_hhmm(self.start) >= parse_hhmm(self.end):
            raise ValueError(f"opening {self.start} must be before closing {self.end}")
        return self


class ClinicHours(BaseModel):
    """Opening ranges per weekday. An empty list is a closed day."""

    model_config = ConfigDict(extra="forbid")

    mon: list[TimeRange] = Field(default_factory=list)
    tue: list[TimeRange] = Field(default_factory=list)
    wed: list[TimeRange] = Field(default_factory=list)
    thu: list[TimeRange] = Field(default_factory=list)
    fri: list[TimeRange] = Field(default_factory=list)
    sat: list[TimeRange] = Field(default_factory=list)
    sun: list[TimeRange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_overlaps(self) -> "ClinicHours":
        for day in WEEKDAYS:
            ranges = sorted(
                getattr(self, day), key=lambda r: parse_hhmm(r.start)
            )
            if len(ranges) > MAX_RANGES_PER_DAY:
                raise ValueError(
                    f"{day}: at most {MAX_RANGES_PER_DAY} opening ranges per day"
                )
            for earlier, later in zip(ranges, ranges[1:]):
                if parse_hhmm(later.start) < parse_hhmm(earlier.end):
                    raise ValueError(
                        f"{day}: {earlier.start}-{earlier.end} overlaps "
                        f"{later.start}-{later.end}"
                    )
            setattr(self, day, ranges)
        return self


class PracticeSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clinic_hours: ClinicHours
    appointment_minutes: int = Field(..., ge=5, le=240)


def _spoken_name(value: str) -> str:
    """A name the agent will say aloud: one plain line, no template syntax.

    Braces are refused because the agent prompt is a template — a name holding
    "{{" would be a way to write into it. Newlines because a name is one line.
    """
    value = " ".join(value.split())
    if not value:
        raise ValueError("must not be empty")
    if any(ch in value for ch in "{}<>"):
        raise ValueError("may not contain { } < or >")
    return value


class PracticeProfileUpdate(BaseModel):
    """How the agent names the doctor and the practice on every call."""

    model_config = ConfigDict(extra="forbid")

    doctor_name: str = Field(..., max_length=80, description='e.g. "Dr. Rahbir Mahdi"')
    practice_name: str = Field(..., max_length=100, description='e.g. "Green Life Clinic"')

    @field_validator("doctor_name", "practice_name")
    @classmethod
    def _plain(cls, value: str) -> str:
        return _spoken_name(value)


class PracticeSettingsRead(BaseModel):
    """What the settings page shows.

    `clinic_hours` is null until the practice saves it; until then the agent
    offers no times and says the practice will call back. `timezone` is
    read-only here — it is the deployment's DEFAULT_TIMEZONE, the zone the
    hours are read in.
    """

    clinic_hours: ClinicHours | None
    appointment_minutes: int
    timezone: str
    # null until the doctor sets them; the agent then falls back to the
    # patient's recorded physician and to PRACTICE_NAME.
    doctor_name: str | None = None
    practice_name: str | None = None
