"""Resource-specific HEXA routes attached to an immutable Scouter baseline."""

RESOURCES = {"fragments": "Fragments", "sol_erda": "Sol Erda"}


def validate_resource(resource):
    if not isinstance(resource, str) or resource not in RESOURCES:
        raise ValueError("Choose Fragments or Sol Erda for the HEXA route")
    return resource


def saved_order(record, resource):
    validate_resource(resource)
    route = record.get("hexa_orders", {}).get(resource, {})
    order = route.get("order")
    if order is None and resource == "fragments":
        order = record.get("order")
    return order if isinstance(order, dict) and isinstance(order.get("class_hexa"), list) else None
