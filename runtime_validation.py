"""V2 runtime validation helpers.

The model is untrusted input. Before the Runtime acts on a model response, it
validates the response shape. This module intentionally stays deterministic and
provider-agnostic.
"""


def validate_model_response(response) -> dict:
    """Validate the tiny Runtime-facing model contract.

    Valid responses are either:
      {"type": "final", "content": "..."}
    or:
      {
        "type": "tool_call",
        "tool_name": "calculator",
        "arguments": {...},
        ...
      }
    """
    if not isinstance(response, dict):
        return {
            "ok": False,
            "error": {
                "code": "invalid_model_response",
                "message": "Model response must be a dictionary.",
            },
        }

    response_type = response.get("type")
    if response_type == "final":
        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            return {
                "ok": False,
                "error": {
                    "code": "invalid_final_response",
                    "message": "Final response requires non-empty string content.",
                },
            }
        return {"ok": True}

    if response_type == "tool_call":
        tool_name = response.get("tool_name")
        arguments = response.get("arguments")

        if not isinstance(tool_name, str) or not tool_name.strip():
            return {
                "ok": False,
                "error": {
                    "code": "invalid_tool_call",
                    "message": "Tool call requires a non-empty tool_name.",
                },
            }

        if not isinstance(arguments, dict):
            return {
                "ok": False,
                "error": {
                    "code": "invalid_tool_call",
                    "message": "Tool call arguments must be a dictionary.",
                },
            }

        return {"ok": True}

    return {
        "ok": False,
        "error": {
            "code": "unknown_model_response_type",
            "message": f"Unsupported model response type: {response_type!r}.",
        },
    }
