import logging
import time
import grpc

logger = logging.getLogger("grpc.logging_interceptor")


class LoggingInterceptor(grpc.ServerInterceptor):
    """gRPC Server Interceptor to log RPC execution and duration."""

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None:
            return None

        method = handler_call_details.method

        if handler.unary_unary:
            def unary_unary_wrapper(request, context):
                start = time.perf_counter()
                try:
                    result = handler.unary_unary(request, context)
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.debug(f"[gRPC] Unary {method} succeeded in {duration_ms:.2f}ms")
                    return result
                except Exception:
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.warning(f"[gRPC] Unary {method} failed after {duration_ms:.2f}ms")
                    raise

            return grpc.unary_unary_rpc_method_handler(
                unary_unary_wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:
            def unary_stream_wrapper(request, context):
                start = time.perf_counter()
                try:
                    for resp in handler.unary_stream(request, context):
                        yield resp
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.debug(f"[gRPC] Stream {method} completed in {duration_ms:.2f}ms")
                except Exception:
                    duration_ms = (time.perf_counter() - start) * 1000
                    logger.warning(f"[gRPC] Stream {method} failed after {duration_ms:.2f}ms")
                    raise

            return grpc.unary_stream_rpc_method_handler(
                unary_stream_wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler
