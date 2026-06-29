"""Abstract interface for rendering to different outputs."""
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from PIL import ImageDraw


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


class PILRenderer(Renderer):
    """Renderer that outputs to PIL Image (for testing/debugging)."""

    def __init__(self, size: Tuple[int, int] = (800, 480), output_path: Optional[str] = None):
        """Initialize PIL renderer.
        
        Args:
            size: Display size as (width, height)
            output_path: Optional path to save output BMP file
        """
        from PIL import Image

        self.size = size
        self.output_path = output_path or "output.bmp"
        self.image = Image.new("1", size, color=255)  # 1-bit (black/white)
        self.draw = ImageDraw.Draw(self.image)

    def get_draw(self) -> ImageDraw.ImageDraw:
        """Get PIL draw context."""
        return self.draw

    def render(self) -> None:
        """Save rendered image to file."""
        self.image.save(self.output_path, "BMP")
        print(f"Rendered to {self.output_path}")

    def get_size(self) -> Tuple[int, int]:
        """Get display size."""
        return self.size

    def clear(self) -> None:
        """Clear the display."""
        from PIL import Image

        self.image = Image.new("1", self.size, color=255)
        self.draw = ImageDraw.Draw(self.image)

    def get_image(self):
        """Get the underlying PIL Image (for inspection in tests)."""
        return self.image
