from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Transaction Graph Intelligence Engine"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    # Plain string — never parsed as JSON, safe with any env var value
    ALLOWED_ORIGINS: str = "*"

    # Database (optional — not required for demo mode)
    DATABASE_URL: str = ""

    # Simulation
    SIMULATION_FRAUD_PROBABILITY: float = 0.12
    MAX_ACCOUNTS: int = 80
    NORMAL_ACCOUNTS: int = 50
    MULE_ACCOUNTS: int = 20
    HIGH_RISK_ACCOUNTS: int = 10

    # Graph Engine — kept low to stay within Railway free-tier RAM
    GRAPH_MAX_NODES: int = 150
    GRAPH_MAX_EDGES: int = 600
    CYCLE_DETECTION_DEPTH: int = 5

    # Anomaly Detection
    ISOLATION_FOREST_CONTAMINATION: float = 0.1
    ANOMALY_SCORE_THRESHOLD: float = 0.65
    VELOCITY_WINDOW_SECONDS: int = 60
    FAN_OUT_THRESHOLD: int = 5
    RAPID_TXN_THRESHOLD: int = 10

    # WebSocket
    WS_BROADCAST_INTERVAL: float = 1.0    # seconds between graph broadcasts
    WS_MAX_CONNECTIONS: int = 20

    # Blue Team integration (separate service — gracefully degrades if offline)
    BLUE_TEAM_URL: str = "http://localhost:8001"
    BLUE_TEAM_API_KEY: str = "changeme-graph-engine-key"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
