import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    carrier_url: str = os.environ.get("CARRIER_URL", "http://carrier-stub:8001")
    model_mode: str = os.environ.get("MODEL_MODE", "replay")
    data_class: str = os.environ.get("DATA_CLASS", "internal")


settings = Settings()
