import os

os.environ.setdefault("MODEL_MODE", "rules")
os.environ.setdefault("DATA_CLASS", "pii")
os.environ.setdefault("ALLOWED_ORDER_FIELDS", "status,eta,items_count")
