# Session 3 Architecture

```text
Tkinter GUI / experiment runner
          |
          +-- InProcessAnalyticsAdapter ---------+
          +-- RestAnalyticsAdapter -> REST/JSON -+--> RetailMetricsServiceCore
          +-- GrpcAnalyticsAdapter -> gRPC/proto -+             |
                                                               v
                                             immutable canonical snapshot
                                                               |
                                             read-only PostgreSQL repository
```

REST and gRPC are transport mappings around the same `RetailMetricsServiceCore`; neither contains separate business calculations. The core is built from canonical/imported data and then treated as immutable for an experiment run. Monetary values cross the protobuf boundary as integer cents produced directly from PostgreSQL `Decimal` values.

The REST server is FastAPI/Uvicorn on `127.0.0.1:8100`. The gRPC server is `grpcio` on `127.0.0.1:50051`. They are deliberately not LAN-facing. PostgreSQL remains localhost-only.

The `.proto` contract is the source of truth. Generated modules are committed build outputs and are regenerated only by `GENERATE_PROTO.bat`, never by the GUI.
