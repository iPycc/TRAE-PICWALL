from typing import Any


def ok(data: Any = None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"data": data if data is not None else {}}
    if meta is not None:
        payload["meta"] = meta
    return payload


def page(data: list[Any], page_number: int, page_size: int, total: int) -> dict[str, Any]:
    return {"data": data, "meta": {"page": page_number, "page_size": page_size, "total": total}}

