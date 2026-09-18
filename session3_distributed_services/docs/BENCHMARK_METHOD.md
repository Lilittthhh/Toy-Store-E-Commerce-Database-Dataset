# Benchmark Method

All values are measured locally and must be interpreted as observations of this implementation and machine.

- **Payload size:** byte length of compact UTF-8 JSON and deterministic protobuf serialization of equivalent application messages. HTTP/2, TCP, and other framing are excluded.
- **Unary latency:** warm-up calls precede timed calls. Reports contain call count, median, p95, calls per second, and serialized response bytes for in-process, REST/JSON, and gRPC/protobuf paths.
- **Round trips:** N individual order requests are compared with one batch request containing the same IDs. Equality is mandatory; timing is descriptive.
- **Streaming:** a unary response and server stream return the same ordered session metrics. Time to first streamed message and both total completion times are reported separately. Streaming is not assumed to minimize total time.
- **Adapter swap:** one transport-neutral caller runs through REST and gRPC adapters. Normalized results must be identical and the caller site remains unchanged.
- **Deadline:** the same read-only diagnostic call is first given an intentionally insufficient timeout and then a generous timeout. Expected behavior is `DEADLINE_EXCEEDED` followed by success.

Correctness tests validate equality and measurement structure. They intentionally do not require one protocol to outperform another.
