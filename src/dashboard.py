"""Main orchestrator for the dashboard."""
from typing import List
from rendering.renderer import Renderer
from components.widget import Widget


class Dashboard:
    """Main orchestrator that manages widgets and rendering."""

    def __init__(self, renderer: Renderer):
        """Initialize dashboard.
        
        Args:
            renderer: Rendering backend (PIL, hardware, etc.)
        """
        self.renderer = renderer
        self.widgets: List[Widget] = []

    def add_widget(self, widget: Widget) -> None:
        """Add a widget to the dashboard.
        
        Args:
            widget: Widget instance to add
        """
        self.widgets.append(widget)

    def update_all(self) -> None:
        """Update all widgets (fetch fresh data if needed)."""
        for widget in self.widgets:
            widget.update()

    def render(self) -> None:
        """Render all widgets to the output."""
        for widget in self.widgets:
            widget.render()

        self.renderer.render()

    def run(self) -> None:
        """Main run loop: update and render."""
        self.update_all()
        self.render()
