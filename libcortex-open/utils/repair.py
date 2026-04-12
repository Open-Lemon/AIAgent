from typing import Optional, Any
import ast
import json
from json import JSONDecodeError

import json5
from json_repair import loads


def structure_output_repair(string_input: Optional[str] = None) -> Any:
    # borrowed from CrewAI
    if string_input is None:
        return string_input

    if not string_input.strip():
        return ""

    if not isinstance(string_input, str) or not string_input.strip():
        raise Exception(
            "Tool input must be a valid dictionary in JSON or Python literal format"
        )

    # Attempt 1: Parse as JSON
    try:
        structure_output = json.loads(string_input)
        return structure_output
    except (JSONDecodeError, TypeError):
        pass  # Continue to the next parsing attempt

    # Attempt 2: Parse as Python literal
    try:
        structure_output = ast.literal_eval(string_input)
        return structure_output
    except (ValueError, SyntaxError, TypeError):
        pass  # Continue to the next parsing attempt

    # Attempt 3: Parse as JSON5
    try:
        structure_output = json5.loads(string_input)
        return structure_output
    except (JSONDecodeError, ValueError, TypeError):
        pass  # Continue to the next parsing attempt

    # Attempt 4: Repair JSON
    try:
        structure_output = loads(string_input)
        return structure_output
    except Exception as e:
        error = f"Failed to repair JSON: {e}"

    error_message = (
        "Tool input must be a valid dictionary in JSON or Python literal format"
    )
    # If all parsing attempts fail, raise an error
    raise Exception(error_message)


if __name__ == "__main__":
    print(structure_output_repair(r'{{"hello": "world", "test_key": "test_value"}}'))