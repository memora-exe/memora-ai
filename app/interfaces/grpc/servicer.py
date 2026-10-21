import os
import sys
from typing import Iterator, Optional

# Ensure generated protobuf modules can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
proto_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "proto"))
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

from ai.v1 import ai_service_pb2 as pb2
from ai.v1 import ai_service_pb2_grpc as pb2_grpc

from ...ports.document_parser import DocumentParserPort
from ...ports.embedder import EmbedderPort
from ...ports.reranker import RerankerPort
from ...ports.llm import LlmPort
from ...ports.graph_ml import GraphMlPort

from ...infrastructure.adapters.document_parser_adapter import DocumentParserAdapter
from ...infrastructure.adapters.embedder_adapter import EmbedderAdapter, EmbeddingAdapter
from ...infrastructure.adapters.reranker_adapter import RerankerAdapter, RerankAdapter
from ...infrastructure.adapters.llm_adapter import LlmAdapter
from ...infrastructure.adapters.graph_ml_adapter import GraphMlAdapter

from .mapper import (
    map_proto_messages_to_domain,
    map_proto_edges_to_domain,
    to_proto_parse_response,
    to_proto_embedding_response,
    to_proto_rerank_response,
    to_proto_chat_completion,
    to_proto_chat_chunk,
    to_proto_detect_communities,
)


class DocumentParserServicer(pb2_grpc.DocumentParserServiceServicer):
    """gRPC servicer for document parsing delegating to DocumentParserPort."""

    def __init__(self, parser: Optional[DocumentParserPort] = None):
        self.parser = parser or DocumentParserAdapter()

    def ParseDocument(self, request: pb2.ParseDocumentRequest, context) -> pb2.ParseDocumentResponse:
        result = self.parser.parse_document(
            file_content=request.file_content,
            file_name=request.file_name or "document",
            mime_type=request.mime_type or "",
            options=dict(request.options or {}),
        )
        return to_proto_parse_response(result)


class EmbeddingServicer(pb2_grpc.EmbeddingServiceServicer):
    """gRPC servicer for vector embeddings delegating to EmbedderPort."""

    def __init__(self, embedder: Optional[EmbedderPort] = None):
        self.embedder = embedder or EmbedderAdapter()

    def GenerateEmbeddings(
        self, request: pb2.GenerateEmbeddingsRequest, context
    ) -> pb2.GenerateEmbeddingsResponse:
        texts = list(request.texts)
        model = request.model or "text-embedding-004"
        dimensions = request.dimensions if request.dimensions > 0 else 768

        result = self.embedder.generate_embeddings(texts=texts, model=model, dimensions=dimensions)
        return to_proto_embedding_response(result)


class RerankServicer(pb2_grpc.RerankServiceServicer):
    """gRPC servicer for candidate reranking delegating to RerankerPort."""

    def __init__(self, reranker: Optional[RerankerPort] = None):
        self.reranker = reranker or RerankerAdapter()

    def Rerank(self, request: pb2.RerankRequest, context) -> pb2.RerankResponse:
        results = self.reranker.rerank(
            query=request.query or "",
            documents=list(request.documents),
            top_n=request.top_n if request.top_n > 0 else 0,
        )
        return to_proto_rerank_response(results)


class LlmServicer(pb2_grpc.LlmServiceServicer):
    """gRPC servicer for LLM completion and streaming delegating to LlmPort."""

    def __init__(self, llm: Optional[LlmPort] = None):
        self.llm = llm or LlmAdapter()

    def ChatCompletion(
        self, request: pb2.ChatCompletionRequest, context
    ) -> pb2.ChatCompletionResponse:
        messages = map_proto_messages_to_domain(request.messages)
        result = self.llm.chat_completion(
            messages=messages,
            model=request.model or "gemini-2.5-flash",
            temperature=request.temperature or 0.7,
        )
        return to_proto_chat_completion(result)

    def ChatCompletionStream(
        self, request: pb2.ChatCompletionRequest, context
    ) -> Iterator[pb2.ChatCompletionChunk]:
        messages = map_proto_messages_to_domain(request.messages)
        for chunk in self.llm.chat_completion_stream(
            messages=messages,
            model=request.model or "gemini-2.5-flash",
            temperature=request.temperature or 0.7,
        ):
            yield to_proto_chat_chunk(chunk)


class GraphMlServicer(pb2_grpc.GraphMlServiceServicer):
    """gRPC servicer for graph community detection delegating to GraphMlPort."""

    def __init__(self, graph_ml: Optional[GraphMlPort] = None):
        self.graph_ml = graph_ml or GraphMlAdapter()

    def DetectCommunities(
        self, request: pb2.DetectCommunitiesRequest, context
    ) -> pb2.DetectCommunitiesResponse:
        edges = map_proto_edges_to_domain(request.edges)
        results = self.graph_ml.detect_communities(
            node_ids=list(request.node_ids),
            edges=edges,
            algorithm=request.algorithm or "louvain",
        )
        return to_proto_detect_communities(results)
