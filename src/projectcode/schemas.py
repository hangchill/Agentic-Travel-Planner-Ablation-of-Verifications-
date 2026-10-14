"""Diagram-aligned seven-day sandbox records and agent workflow contracts.

The table models mirror documents/travel_planner_data_schema.png. SandboxData
validates relational keys; individual records cannot validate foreign keys alone.
Workflow Constraint/Itinerary/Check/State remain separate from environment tables.
"""
from decimal import Decimal
import re
from typing import Annotated, Any, Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field, model_validator


Identifier = Annotated[str, Field(strict=True, min_length=1)]
DayIndex = Annotated[int, Field(strict=True, ge=1, le=7)]
StartMinute = Annotated[int, Field(strict=True, ge=0, lt=1440)]
EndMinute = Annotated[int, Field(strict=True, ge=0, le=1440)]
PositiveInteger = Annotated[int, Field(strict=True, gt=0)]
NonnegativeInteger = Annotated[int, Field(strict=True, ge=0)]
NonnegativeDecimal = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
NullableBoolean = Annotated[bool, Field(strict=True)] | None


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Area(Record):
    area_id: Identifier
    area_name: Identifier


class Location(Record):
    location_id: Identifier
    location_type: Identifier
    name: Identifier
    area_id: Identifier
    tags: list[Identifier]
    wheelchair_accessible: NullableBoolean = None


class MinuteWindow(Record):
    """Shared interval validation. End may be 1440 (the end of that day)."""
    day_index: DayIndex
    start_minute: StartMinute
    end_minute: EndMinute

    @model_validator(mode='after')
    def ordered_interval(self):
        if self.end_minute <= self.start_minute:
            raise ValueError('end_minute must be greater than start_minute')
        return self


class Weather(MinuteWindow):
    area_id: Identifier
    condition: Identifier


class OpeningWindow(MinuteWindow):
    opening_window_id: Identifier
    location_id: Identifier


class Attraction(Record):
    location_id: Identifier
    category: Identifier
    admission_price_per_person: NonnegativeDecimal
    visit_duration_minutes: PositiveInteger
    outdoor_exposure: Identifier


class Restaurant(Record):
    location_id: Identifier
    cuisine_types: list[Identifier]
    dietary_options: list[Identifier]
    meal_price_min_per_person: NonnegativeDecimal
    meal_price_max_per_person: NonnegativeDecimal
    meal_duration_minutes: PositiveInteger

    @model_validator(mode='after')
    def ordered_prices(self):
        if self.meal_price_max_per_person < self.meal_price_min_per_person:
            raise ValueError('meal_price_max_per_person must be >= meal_price_min_per_person')
        return self


class Accommodation(Record):
    location_id: Identifier
    price_per_room_per_night: NonnegativeDecimal
    room_capacity: PositiveInteger
    amenities: list[Identifier]


class TransportMode(Record):
    mode_id: Identifier
    base_fare: NonnegativeDecimal
    rate_per_km: NonnegativeDecimal
    fare_basis: Identifier
    vehicle_capacity: PositiveInteger | None = None


class TravelMatrixEntry(Record):
    from_location_id: Identifier
    to_location_id: Identifier
    mode_id: Identifier
    distance_km: NonnegativeDecimal
    travel_time_minutes: NonnegativeInteger


class SandboxData(Record):
    """Validated table bundle; no CSV loading or invented missing evidence.

    location_type values are attraction, restaurant or accommodation in this
    application's bundle. The diagram leaves the string vocabulary unspecified;
    these names are the explicit integration convention matching its subtypes.
    Empty tables are allowed, but every supplied location needs exactly one subtype.
    """
    areas: list[Area] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    weather: list[Weather] = Field(default_factory=list)
    opening_windows: list[OpeningWindow] = Field(default_factory=list)
    attractions: list[Attraction] = Field(default_factory=list)
    restaurants: list[Restaurant] = Field(default_factory=list)
    accommodations: list[Accommodation] = Field(default_factory=list)
    transport_modes: list[TransportMode] = Field(default_factory=list)
    travel_matrix: list[TravelMatrixEntry] = Field(default_factory=list)

    @model_validator(mode='after')
    def relational_integrity(self):
        def keys(table, fields):
            rows = getattr(self, table)
            values = [tuple(getattr(row, field) for field in fields) for row in rows]
            if len(values) != len(set(values)):
                raise ValueError(f'Duplicate primary key in {table}: {fields}')
            return {value[0] for value in values} if len(fields) == 1 else set(values)

        area_ids = keys('areas', ('area_id',))
        location_ids = keys('locations', ('location_id',))
        mode_ids = keys('transport_modes', ('mode_id',))
        keys('weather', ('area_id', 'day_index', 'start_minute'))
        keys('opening_windows', ('opening_window_id',))
        keys('travel_matrix', ('from_location_id', 'to_location_id', 'mode_id'))
        subtype_ids = {kind: keys(table, ('location_id',)) for kind, table in (
            ('attraction', 'attractions'), ('restaurant', 'restaurants'),
            ('accommodation', 'accommodations'))}

        def require(table, field, expected):
            for row in getattr(self, table):
                if getattr(row, field) not in expected:
                    raise ValueError(f'Unknown foreign key in {table}.{field}: {getattr(row, field)}')

        require('locations', 'area_id', area_ids)
        require('weather', 'area_id', area_ids)
        for table in ('opening_windows', 'attractions', 'restaurants', 'accommodations'):
            require(table, 'location_id', location_ids)
        require('travel_matrix', 'from_location_id', location_ids)
        require('travel_matrix', 'to_location_id', location_ids)
        require('travel_matrix', 'mode_id', mode_ids)
        for location in self.locations:
            kinds = [kind for kind, ids in subtype_ids.items() if location.location_id in ids]
            if kinds != [location.location_type]:
                raise ValueError('Each location requires exactly one matching subtype: ' + location.location_id)
        return self

    def validate_itinerary(self, plan):
        """Validate activity references against this bundle, not all travel constraints."""
        itinerary = Itinerary.model_validate(plan)
        location_ids = {location.location_id for location in self.locations}
        for day in itinerary.days:
            for activity in day.activities:
                if activity.location_id not in location_ids:
                    raise ValueError('Activity has missing/unknown location_id: ' + activity.activity_id)
        return itinerary


class Constraint(Record):
    constraint_id: str = Field(min_length=1)
    type: str
    category: str
    operator: str
    value: Any
    hardness: Literal['hard', 'soft']
    explicitness: Literal['explicit', 'implicit']
    verification: str


class Activity(Record):
    activity_id: str = Field(min_length=1)
    location_id: Identifier | None = None
    name: str
    category: str | None = None
    start_minute: StartMinute | None = None
    end_minute: EndMinute | None = None
    location: str | None = None
    price_usd: NonnegativeDecimal | None = None

    @model_validator(mode='before')
    @classmethod
    def legacy_fields(cls, value):
        """Normalize old notebook/fixture fields into one canonical representation."""
        if not isinstance(value, dict):
            return value
        value = value.copy()
        if 'venue_id' in value:
            legacy = value.pop('venue_id')
            if 'location_id' in value and value['location_id'] != legacy:
                raise ValueError('Conflicting location_id and legacy venue_id')
            value['location_id'] = legacy
        for old, new in (('start_time', 'start_minute'), ('end_time', 'end_minute')):
            if old not in value:
                continue
            clock = value.pop(old)
            minute = None
            if clock is not None:
                if not isinstance(clock, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d|24:00', clock):
                    raise ValueError(old + ' must be HH:MM or null')
                hour, mins = map(int, clock.split(':'))
                minute = hour * 60 + mins
            if new in value and value[new] != minute:
                raise ValueError('Conflicting ' + new + ' and legacy ' + old)
            value[new] = minute
        return value

    @model_validator(mode='after')
    def ordered_times(self):
        if self.start_minute is not None and self.end_minute is not None and self.end_minute <= self.start_minute:
            raise ValueError('Activity end_minute must be greater than start_minute')
        return self

    @property
    def venue_id(self):
        """Legacy read accessor; serialized plans use location_id only."""
        return self.location_id


class Day(Record):
    day_index: DayIndex
    activities: list[Activity] = Field(default_factory=list)


class Itinerary(Record):
    destination: str | None = None
    days: list[Day] = Field(min_length=1, max_length=7)
    total_cost_usd: NonnegativeDecimal | None = None
    summary: str | None = None

    @model_validator(mode='after')
    def identities(self):
        if [d.day_index for d in self.days] != list(range(1, len(self.days) + 1)):
            raise ValueError('day_index must be consecutive from 1')
        ids = [a.activity_id for d in self.days for a in d.activities]
        if len(set(ids)) != len(ids):
            raise ValueError('activity_id must be unique across the itinerary')
        return self


class Check(Record):
    constraint_id: str
    status: Literal['PASS', 'FAIL', 'UNVERIFIABLE']
    evidence: str = ''
    # Scope is provided by trusted verifier/caller, never by the repair model.
    activity_ids: list[str] = Field(default_factory=list)
    failure_kind: Literal['constraint_violation', 'missing_information', 'unsupported_claim', 'hard_conflict'] | None = None
    conflict_proven: bool = False

    @model_validator(mode='after')
    def finding_consistency(self):
        if self.failure_kind is not None and self.status == 'PASS':
            raise ValueError('A failure finding cannot be PASS')
        if self.conflict_proven and (self.failure_kind != 'hard_conflict' or self.status != 'FAIL' or not self.evidence.strip()):
            raise ValueError('A proven conflict requires hard_conflict, FAIL and evidence')
        return self


class State(TypedDict, total=False):
    request: str
    constraints: list[dict]
    info: dict
    draft: dict
    final: dict
    recovery_result: dict
