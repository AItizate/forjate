from .config import settings


def classify_damage(report: dict) -> str:
    # SEAM damage-classifier: the live model classifies the report text (backlog); replay returns the seed's label
    if settings.model_mode == "replay":
        return report["label"]
    raise NotImplementedError("live classification is backlog ticket T-damage-classifier")
