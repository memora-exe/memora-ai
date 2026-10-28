"""gRPC Server entrypoint for memora-ai LibIOG3 Architecture.
Runs stateless technical services for AI, ML, Parsing, Reranking, and Graph clustering.
"""
import logging
import os
import signal
import sys
import time
from concurrent import futures
from typing import Optional, Sequence

import grpc

# Ensure generated protobuf modules can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
proto_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "proto"))
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

from ai.v1 import ai_service_pb2_grpc as pb2_grpc
from .servicer import (
    DocumentParserServicer,
    GraphMlServicer,
    LlmServicer,
    RerankServicer,
)
from .interceptors import ErrorInterceptor, LoggingInterceptor
from ...infrastructure.config.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("memora-ai-grpc")


def create_server(
    max_workers: int = 10,
    interceptors: Optional[Sequence[grpc.ServerInterceptor]] = None,
) -> grpc.Server:
    """Create and configure gRPC server with interceptors and all 4 stateless servicers."""
    server_interceptors = list(interceptors) if interceptors is not None else [
        LoggingInterceptor(),
        ErrorInterceptor(),
    ]

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        interceptors=server_interceptors,
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),
        ],
    )

    # Register servicers
    pb2_grpc.add_DocumentParserServiceServicer_to_server(DocumentParserServicer(), server)
    pb2_grpc.add_RerankServiceServicer_to_server(RerankServicer(), server)
    pb2_grpc.add_LlmServiceServicer_to_server(LlmServicer(), server)
    pb2_grpc.add_GraphMlServiceServicer_to_server(GraphMlServicer(), server)

    return server


def serve():
    """Start gRPC server and wait for termination."""
    port = settings.grpc_port
    server = create_server(max_workers=settings.max_workers)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    logger.info(f"Stateless AI gRPC Server running on port {port}")

    def handle_shutdown(signum, frame):
        logger.info("Received termination signal, shutting down gracefully...")
        server.stop(grace=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(grace=5)


if __name__ == "__main__":
    serve()
