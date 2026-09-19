"""The shape of a validated house configuration.

This is the only layer below `sources/` that is allowed to know an entity id
exists, because mapping rooms to entity ids is precisely what configuration is
for (INTENT.md section 6). The objects here carry identity, comfort and entity
references; turning a reference into a reading is the source layer's job, and
nothing above it ever sees an `EntityRef`.

There are no pixel coordinates here and there is no place to put one. Layout is
computed from a box model, never configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.models import ComfortBand


@dataclass(frozen=True)
class EntityRef:
    """Where one value comes from.

    Usually a whole entity, whose state is the value. When `attribute` is set,
    the value is that attribute of the entity instead - which is how an outdoor
    row can be backed by the weather provider rather than by a physical sensor.
    """

    entity_id: str
    attribute: str | None = None

    def __str__(self) -> str:
        if self.attribute is None:
            return self.entity_id
        return f"{self.entity_id}[{self.attribute}]"


@dataclass(frozen=True)
class DeviceConfig:
    """A device attached to a room.

    Modelled from day one and rendered by nobody yet (INTENT.md section 5).
    `kind` is an open string for the same reason it is open in the domain.
    """

    key: str
    name: str
    kind: str
    source: EntityRef


@dataclass(frozen=True)
class RoomConfig:
    """One row of the room table, before any reading has been fetched.

    `order` is not configurable: it is the room's position in the file. Two
    places to state the same ordering is one place too many.
    """

    key: str
    name: str
    order: int = 0
    icon: str | None = None
    is_outdoor: bool = False
    temperature: EntityRef | None = None
    humidity: EntityRef | None = None
    climate: EntityRef | None = None
    comfort: ComfortBand = field(default_factory=ComfortBand)
    devices: tuple[DeviceConfig, ...] = ()

    @property
    def entity_refs(self) -> tuple[EntityRef, ...]:
        """Every reference this room needs, climate readings and devices alike."""
        refs = [ref for ref in (self.temperature, self.humidity, self.climate) if ref is not None]
        refs.extend(device.source for device in self.devices)
        return tuple(refs)


@dataclass(frozen=True)
class HouseConfig:
    """The whole file, validated.

    Reaching this type means the configuration was well-formed; a bad config is
    a developer error and never becomes a `HouseConfig`. A *missing sensor* is
    an entirely different thing - that is a normal runtime state and shows up
    as `None` further up.
    """

    weather: EntityRef
    sun: EntityRef
    rooms: tuple[RoomConfig, ...] = ()

    def room(self, key: str) -> RoomConfig:
        """The room with this key, or KeyError."""
        for room in self.rooms:
            if room.key == key:
                return room
        raise KeyError(key)

    @property
    def indoor_rooms(self) -> tuple[RoomConfig, ...]:
        """Everything except the outdoor row."""
        return tuple(room for room in self.rooms if not room.is_outdoor)

    @property
    def entity_refs(self) -> tuple[EntityRef, ...]:
        """Every reference in the file, rooms first, then weather and sun."""
        refs: list[EntityRef] = []
        for room in self.rooms:
            refs.extend(room.entity_refs)
        refs.extend((self.weather, self.sun))
        return tuple(refs)

    @property
    def entity_ids(self) -> tuple[str, ...]:
        """The distinct entity ids the configuration depends on, in file order.

        This is what a source fetches and what the capture tool audits against
        the live instance.
        """
        seen: dict[str, None] = {}
        for ref in self.entity_refs:
            seen.setdefault(ref.entity_id, None)
        return tuple(seen)
