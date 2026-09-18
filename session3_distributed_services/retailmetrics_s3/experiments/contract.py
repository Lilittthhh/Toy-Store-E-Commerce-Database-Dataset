from __future__ import annotations

import importlib
from pathlib import Path

from ..artifacts import write_json
from ..proto import retailmetrics_pb2 as pb


def contract_report(output: Path | None = None) -> dict:
    descriptor = pb.DESCRIPTOR
    messages = []
    for message in descriptor.message_types_by_name.values():
        fields = []
        for field in message.fields:
            if field.message_type is not None:
                type_name = field.message_type.full_name
            elif field.enum_type is not None:
                type_name = field.enum_type.full_name
            else:
                type_name = str(field.type)
            fields.append({
                "number": field.number,
                "name": field.name,
                "type": type_name,
                "wire_type": _wire_type(field.type),
                "repeated": field.is_repeated,
            })
        messages.append({"name": message.name, "fields": fields})
    services = []
    for service in descriptor.services_by_name.values():
        services.append({
            "name": service.name,
            "methods": [{
                "name": method.name,
                "request": method.input_type.name,
                "response": method.output_type.name,
                "kind": "server-streaming" if method.server_streaming else "unary",
            } for method in service.methods],
        })
    report = {
        "package": descriptor.package,
        "messages": messages,
        "services": services,
        "message_count": len(messages),
        "field_count": sum(len(v["fields"]) for v in messages),
        "service_count": len(services),
        "method_count": sum(len(v["methods"]) for v in services),
        "generated_modules_importable": verify_generated_modules(),
        "passed": True,
    }
    if output:
        write_json(output, report)
    return report


def verify_generated_modules() -> bool:
    for name in (
        "retailmetrics_s3.proto.retailmetrics_pb2",
        "retailmetrics_s3.proto.retailmetrics_pb2_grpc",
    ):
        importlib.import_module(name)
    return True


def _wire_type(field_type: int) -> str:
    if field_type in {1, 6, 16}: return "fixed64"
    if field_type in {2, 7, 15}: return "fixed32"
    if field_type in {9, 11, 12}: return "length-delimited"
    return "varint"
