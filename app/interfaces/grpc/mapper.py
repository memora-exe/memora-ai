import os
import sys
from typing import List

# Ensure generated protobuf modules can be imported
current_dir = os.path.dirname(os.path.abspath(__file__))
proto_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "proto"))
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

from ai.v1 import ai_service_pb2 as pb2
from ...ports.document_parser import ParsedDocumentResult
from ...ports.reranker import RankedDocumentData
from ...ports.llm import ChatMessageData, ChatCompletionResult, ChatStreamChunkResult
from ...ports.graph_ml import EdgeData, ClusterAssignmentData


def map_proto_messages_to_domain(proto_messages) -> List[ChatMessageData]:
    return [
        ChatMessageData(role=m.role, content=m.content)
        for m in proto_messages
    ]


def map_proto_edges_to_domain(proto_edges) -> List[EdgeData]:
    return [
        EdgeData(source_id=e.source_id, target_id=e.target_id, weight=float(e.weight) if e.weight > 0 else 1.0)
        for e in proto_edges
    ]


def to_proto_parse_response(result: ParsedDocumentResult) -> pb2.ParseDocumentResponse:
    chunks = [
        pb2.DocumentChunk(
            chunk_index=c.chunk_index,
            content=c.content,
            start_char=c.start_char,
            end_char=c.end_char,
            metadata=c.metadata,
        )
        for c in result.chunks
    ]
    metadata = pb2.DocumentMetadata(
        page_count=result.metadata.page_count,
        word_count=result.metadata.word_count,
        title=result.metadata.title,
        detected_language=result.metadata.detected_language,
    )
    return pb2.ParseDocumentResponse(
        markdown_content=result.markdown_content,
        chunks=chunks,
        metadata=metadata,
    )


def to_proto_rerank_response(results: List[RankedDocumentData]) -> pb2.RerankResponse:
    ranked_docs = [
        pb2.RankedDocument(
            index=r.index,
            score=r.score,
            document=r.document,
        )
        for r in results
    ]
    return pb2.RerankResponse(results=ranked_docs)


def to_proto_chat_completion(result: ChatCompletionResult) -> pb2.ChatCompletionResponse:
    return pb2.ChatCompletionResponse(
        content=result.content,
        tool_calls=[],
        usage=pb2.UsageMetadata(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        ),
        finish_reason=result.finish_reason,
    )


def to_proto_chat_chunk(result: ChatStreamChunkResult) -> pb2.ChatCompletionChunk:
    usage = None
    if result.is_done:
        usage = pb2.UsageMetadata(
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
        )
    return pb2.ChatCompletionChunk(
        delta_content=result.delta_content,
        delta_tool_calls=[],
        usage=usage,
        is_done=result.is_done,
    )


def to_proto_detect_communities(results: List[ClusterAssignmentData]) -> pb2.DetectCommunitiesResponse:
    clusters = [
        pb2.ClusterAssignment(
            cluster_id=c.cluster_id,
            node_ids=c.node_ids,
            metrics=c.metrics,
        )
        for c in results
    ]
    return pb2.DetectCommunitiesResponse(clusters=clusters)
