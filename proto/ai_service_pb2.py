from .ai.v1.ai_service_pb2 import *
from .ai.v1 import ai_service_pb2 as _ai_service_pb2

# Forward all module attributes
for _attr in dir(_ai_service_pb2):
    if not _attr.startswith("_"):
        globals()[_attr] = getattr(_ai_service_pb2, _attr)
