"""Base widget class for dashboard components."""
from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
from core.hass_client import HASSClient
from rendering.renderer import Renderer


class Widget(ABC):
    """Abstract base class for dashboard components.
    
    Each widget:
    - Owns its data fetching from HASS
    - Caches data with optional TTL
    - Knows how to render itself to a drawing context
    """

    def __init__(
        self,
        hass_client: HASSClient,
        renderer: Renderer,
        cache_ttl: Optional[int] = None
    ):
        """Initialize widget.
        
        Args:
            hass_client: Home Assistant client instance
            renderer: Rendering backend (PIL, hardware, etc.)
            cache_ttl: Cache time-to-live in seconds (None = no expiry)
        """
        self.hass_client = hass_client
        self.renderer = renderer
        self.cache_ttl = cache_ttl
        self._last_update: Optional[datetime] = None
        self._data = {}

    def needs_update(self) -> bool:
        """Check if data needs to be refreshed from HASS."""
        if self._last_update is None:
            return True

        if self.cache_ttl is None:
            return False

        elapsed = (datetime.now() - self._last_update).total_seconds()
        return elapsed > self.cache_ttl

    def update(self) -> None:
        """Fetch fresh data from HASS."""
        if not self.needs_update():
            return

        self._fetch_data()
        self._last_update = datetime.now()

    @abstractmethod
    def _fetch_data(self) -> None:
        """Fetch data from HASS client. Subclasses implement this."""
        pass

    @abstractmethod
    def render(self) -> None:
        """Render widget to the current renderer's draw context."""
        pass

    def get_data(self):
        """Get cached data."""
        return self._data
