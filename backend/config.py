"""
Centralized env var configuration via pydantic-settings.
Fails loudly at startup if any required key is missing.
Inject via Depends(get_settings) in routers — never import at module level.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    # External API keys (required)
    openai_api_key: str
    tavily_api_key: str
    brave_search_api_key: str
    google_places_api_key: str
    supabase_url: str
    supabase_service_role_key: str

    # CORS
    frontend_url: str

    # Admin
    admin_key: str = ""

    # Tunable thresholds (have defaults)
    pin_score_threshold: float = 0.0
    pin_laptop_confidence_threshold: float = 0.0
    nearby_search_radius_meters: int = 1500
    place_resolver_similarity_threshold: float = 0.70
    place_resolver_distance_threshold_meters: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
