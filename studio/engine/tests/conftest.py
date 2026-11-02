import os
import tempfile

# Must run before cuestudio.config is imported so tests never write into the repo.
os.environ.setdefault("CUESTUDIO_DATA", tempfile.mkdtemp(prefix="cuestudio_test_"))
