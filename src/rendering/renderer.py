"""Abstract interface for rendering to different outputs."""
from abc import ABC, abstractmethod
import os
from pathlib import Path
from typing import Any, Optional, Tuple

from PIL import ImageDraw, ImageFont


class Renderer(ABC):
    """Abstract base class for rendering to different outputs.
    
    Allows rendering to PIL Image (for testing/debugging) or hardware display.
    """

    @abstractmethod
    def get_draw(self) -> ImageDraw.ImageDraw:
        """Get the drawing context.
        
        Returns:
            PIL ImageDraw object for drawing operations
        """
        pass

    @abstractmethod
    def draw_text(
        self,
        position: Tuple[int, int],
        text: str,
        style: str = "normal",
        fill: int = 0,
    ) -> None:
        """Draw text at a position using a named style.

        Args:
            position: Text position as (x, y)
            text: Content to render
            style: Named style key (small, normal, big)
            fill: Foreground color value
        """
        pass

    @abstractmethod
    def render(self) -> None:
        """Render the current image to the output (screen, file, etc.)."""
        pass

    @abstractmethod
    def get_size(self) -> Tuple[int, int]:
        """Get the display size in pixels.
        
        Returns:
            Tuple of (width, height)
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear the display."""
        pass

    @abstractmethod
    def draw_icon(self, position: Tuple[int, int], name: str, size: int = 100) -> None:
        """Draw a weather icon at a position.

        Args:
            position: Top-left corner as (x, y)
            name: Icon name, e.g. "weather-cloudy"
            size: Icon size in pixels (square); used to locate the BMP file

        Raises:
            FileNotFoundError: If the icon BMP file does not exist
        """
        pass


class PILRenderer(Renderer):
    """Renderer that outputs to PIL Image (for testing/debugging)."""

    def __init__(
        self,
        size: Tuple[int, int] = (800, 480),
        output_path: Optional[str] = None,
        background_path: Optional[str] = None,
    ):
        """Initialize PIL renderer.
        
        Args:
            size: Display size as (width, height)
            output_path: Optional path to save output BMP file
            background_path: Optional path to background BMP file
        """
        self.size = size
        self.output_path = output_path or "output.bmp"
        default_background = os.path.join(
            os.path.dirname(__file__), "..", "..", "assets", "hass-dash-house.bmp"
        )
        self.background_path = background_path or default_background
        self._font_sizes = {"small": 14, "normal": 18, "big": 54}
        self._font_cache: dict[str, Any] = {}
        self._font_bold_path, self._font_regular_path = self._resolve_font_paths()
        self._background_image = self._load_background_image()
        self.image = self._create_base_image()
        self.draw = ImageDraw.Draw(self.image)

    def _load_background_image(self) -> Optional[Any]:
        """Load background image if present and convert to renderer mode."""
        from PIL import Image

        try:
            with Image.open(self.background_path) as loaded:
                image = loaded.convert("1")
                if image.size != self.size:
                    image = image.resize(self.size)
                return image
        except OSError:
            return None

    def _create_base_image(self) -> Any:
        """Create a fresh image for a render pass."""
        from PIL import Image

        if self._background_image is not None:
            return self._background_image.copy()

        return Image.new("1", self.size, color=255)

    def _resolve_font_paths(self) -> Tuple[str, str]:
        """Resolve bold and regular TTF paths from repository assets."""
        fonts_dir = Path(__file__).parent.parent.parent / "assets" / "fonts" / "Liberation"
        bold_path = fonts_dir / "LiberationSans-Bold.ttf"
        regular_path = fonts_dir / "LiberationSans-Regular.ttf"

        missing = [str(path) for path in (bold_path, regular_path) if not path.is_file()]
        if missing:
            missing_str = ", ".join(missing)
            raise FileNotFoundError(f"Required font file(s) not found: {missing_str}")

        return str(bold_path), str(regular_path)

    def _get_font(self, style: str) -> Any:
        """Get a cached PIL font object for the requested style."""
        style_name = style if style in self._font_sizes else "normal"

        cached = self._font_cache.get(style_name)
        if cached is not None:
            return cached

        size = self._font_sizes[style_name]
        font_path = self._font_regular_path if style_name == "small" else self._font_bold_path

        try:
            font = ImageFont.truetype(font_path, size)
        except OSError as exc:
            raise RuntimeError(
                f"Failed to load font '{font_path}' for style '{style_name}' at size {size}"
            ) from exc

        self._font_cache[style_name] = font
        return font

    def get_draw(self) -> ImageDraw.ImageDraw:
        """Get PIL draw context."""
        return self.draw

    def draw_text(
        self,
        position: Tuple[int, int],
        text: str,
        style: str = "normal",
        fill: int = 0,
    ) -> None:
        """Draw text to the image using renderer-managed fonts."""
        font = self._get_font(style)
        self.draw.text(position, text, font=font, fill=fill)

    def render(self) -> None:
        """Save rendered image to file."""
        self.image.save(self.output_path, "BMP")
        print(f"Rendered to {self.output_path}")

    def get_size(self) -> Tuple[int, int]:
        """Get display size."""
        return self.size

    def clear(self) -> None:
        """Clear the display."""
        self.image = self._create_base_image()
        self.draw = ImageDraw.Draw(self.image)

    def draw_icon(self, position: Tuple[int, int], name: str, size: int = 100) -> None:
        """Draw a weather icon from assets at the given position."""
        from PIL import Image, ImageOps

        assets_dir = Path(__file__).parent.parent.parent / "assets" / "weather-icons"
        icon_path = assets_dir / f"{name}-{size}x{size}.bmp"

        if not icon_path.exists():
            raise FileNotFoundError(f"Icon file not found: {icon_path}")

        with Image.open(icon_path) as icon_im:
            inverted = ImageOps.invert(icon_im)
            self.draw.bitmap(position, inverted)

    def get_image(self):
        """Get the underlying PIL Image (for inspection in tests)."""
        return self.image
