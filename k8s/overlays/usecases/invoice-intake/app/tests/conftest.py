import os

# Unit tests need no cluster: a fixed approval secret and the replay model.
os.environ.setdefault("APPROVAL_SECRET", "test-secret")
os.environ.setdefault("MODEL_MODE", "replay")
os.environ.setdefault("DATA_CLASS", "financial")
