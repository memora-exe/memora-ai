"""Entrypoint for memora-ai gRPC Technical Proxy Server (LibIOG3)."""
import os
import sys

# Ensure root directory and proto directory are in sys.path
root_dir = os.path.dirname(os.path.abspath(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

proto_dir = os.path.join(root_dir, "proto")
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

from app.interfaces.grpc.server import serve

if __name__ == "__main__":
    serve()
