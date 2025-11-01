from hass import Client
from localize import local_dt_from_utc_str

test_data = {
    'next_dawn': '2025-11-01T05:43:17.360104+00:00', 
    'next_dusk': '2025-11-01T16:17:40.833431+00:00',
    'next_midnight': '2025-10-31T23:00:55+00:00', 
    'next_noon': '2025-11-01T11:00:55+00:00', 
    'next_rising': '2025-11-01T06:23:08.606893+00:00', 
    'next_setting': '2025-11-01T15:37:53.683560+00:00', 
    'elevation': -26.44, 
    'azimuth': 283.52, 
    'rising': False, 
    'friendly_name': 'Sun'
}

class HassSun:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.data: dict = {}

    def update(self) -> None:
        with self.client:
            sun = self.client.get_entity(entity_id="sun.sun")
            if sun is None:
                raise RuntimeError("Sun entity not found")
            state = sun.get_state()  # Because requests are cached we reduce bandwidth usage :D
            self.data = state.attributes

    def is_night(self) -> bool:
        dawn = self.data.get('next_dawn')
        #dawn_dt = dt.fromisoformat(dawn) if dawn else None
        dawn_dt = local_dt_from_utc_str(dawn) if dawn else None
        dusk = self.data.get('next_dusk')
        #dusk_dt = dt.fromisoformat(dusk) if dusk else None
        dusk_dt = local_dt_from_utc_str(dusk) if dusk else None

        return dawn_dt is not None and dusk_dt is not None and dawn_dt <= dusk_dt
