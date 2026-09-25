import re
from typing import Optional


def validate_slug(value: str) -> str:
    """Validate slug format (lowercase alphanumeric and hyphens)."""
    cleaned = value.strip().lower()
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", cleaned):
        raise ValueError("Slug must contain only lowercase alphanumeric characters and hyphens.")
    return cleaned


def sanitize_string(value: Optional[str]) -> Optional[str]:
    """Strip whitespace and return None if empty."""
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def slugify(text: str) -> str:
    """Generate a clean URL-friendly slug from arbitrary text."""
    if not text:
        return ""
    # Lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")
