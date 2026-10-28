import logging
import grpc

logger = logging.getLogger("grpc.error_interceptor")


class ErrorInterceptor(grpc.ServerInterceptor):
    """gRPC Server Interceptor to catch and handle unhandled exceptions."""

    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None:
            return None

        if handler.unary_unary:
            def unary_unary_wrapper(request, context):
                try:
                    return handler.unary_unary(request, context)
                except Exception as e:
                    logger.exception(f"Unhandled error in unary call {handler_call_details.method}: {e}")
                    context.abort(grpc.StatusCode.INTERNAL, f"Internal server error: {str(e)}")

            return grpc.unary_unary_rpc_method_handler(
                unary_unary_wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        if handler.unary_stream:
            def unary_stream_wrapper(request, context):
                try:
                    for resp in handler.unary_stream(request, context):
                        yield resp
                except Exception as e:
                    logger.exception(f"Unhandled error in streaming call {handler_call_details.method}: {e}")
                    context.abort(grpc.StatusCode.INTERNAL, f"Internal streaming error: {str(e)}")

            return grpc.unary_stream_rpc_method_handler(
                unary_stream_wrapper,
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )

        return handler
