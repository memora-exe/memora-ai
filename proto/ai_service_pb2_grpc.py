from .ai.v1.ai_service_pb2_grpc import *
from .ai.v1 import ai_service_pb2_grpc as _ai_service_pb2_grpc

for _attr in dir(_ai_service_pb2_grpc):
    if not _attr.startswith("_"):
        globals()[_attr] = getattr(_ai_service_pb2_grpc, _attr)
