import json
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from liblogging import logger

from agent_types.common import Tool, ToolCalling


def render_tool_name_description(
    tools: List[Tool],
    with_arguments: bool = False
) -> str:
    """Render the tool name, description, plain text.
    """
    tool_json = []
    for tool in tools:
        if with_arguments:
            tool_json.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema.model_dump(exclude_none=True)
            })
        else:
            tool_json.append({
                "name": tool.name,
                "description": tool.description
            })

    return json.dumps(tool_json, indent=4, ensure_ascii=False)


class ToolCheckerError(Exception):
    """Base exception class for tool checker"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class WrongToolNameError(ToolCheckerError):
    """Exception for tool name related errors"""
    def __init__(self, invalid_name: str, tools_description: str):
        self.invalid_name = invalid_name
        message = f'Invalid tool name "{invalid_name}". Available tools is: {tools_description}'
        super().__init__(message)


class MissRequiredArgumentError(ToolCheckerError):
    """Exception for tool argument related errors"""
    def __init__(self, tool_name: str, missing_args: Optional[List[str]] = None, schema_json: Optional[str] = None):
        self.tool_name = tool_name
        self.missing_args = missing_args or []
        self.schema_json = schema_json

        if missing_args:
            message = f"Missing required arguments for tool '{tool_name}': {', '.join(missing_args)}"
            if schema_json:
                message += f"\nTool's Argument schema: {schema_json}"
        else:
            message = f"Argument validation failed for tool '{tool_name}'"

        super().__init__(message)


class ToolCheckerConfig(BaseModel):
    tool_name_score_threshold: float = Field(
        default=0.85,
        title="Tool Name Score Threshold",
        description="The threshold for matching tool names based on similarity score."
    )


class ToolChecker:
    def __init__(self, config: ToolCheckerConfig):
        self.config = config
        self.tools: List[Tool]

    def _init_tools(self, tools: List[Tool]):
        self.tools = tools

    def _check_tool_name(self, tool_call: ToolCalling) -> str:
        # borrowed from CrewAI
        predict_tool_name = tool_call.name
        order_tools = sorted(
            self.tools,
            key=lambda tool: SequenceMatcher(
                None, tool.name.lower().strip(), predict_tool_name.lower().strip()
            ).ratio(),
            reverse=True,
        )
        for tool in order_tools:
            if (
                tool.name.lower().strip() == predict_tool_name.lower().strip()
                or SequenceMatcher(
                    None, tool.name.lower().strip(), predict_tool_name.lower().strip()
                ).ratio()
                > self.config.tool_name_score_threshold
            ):
                return tool.name
        tools_description = render_tool_name_description(self.tools, with_arguments=False)
        raise WrongToolNameError(predict_tool_name, tools_description)

    def _check_tool_arguments(self, tool_call: ToolCalling, given_tool_name: str) -> Dict[str, Any]:
        tool = next((t for t in self.tools if t.name == given_tool_name), None)
        if not tool:
            raise Exception(f"Tool '{given_tool_name}' not found in tool base")
        # 工具定义中未定义参数，直接返回预测的参数
        if not tool.input_schema:
            return tool_call.arguments

        required_args = tool.input_schema.required or []
        properties = tool.input_schema.properties or {}
        # 检查参数是否缺少
        missing_args = [arg for arg in required_args if arg not in tool_call.arguments]
        if missing_args:
            raise MissRequiredArgumentError(
                tool_name=given_tool_name,
                missing_args=missing_args,
                schema_json=tool.input_schema.model_dump(exclude_none=True)
            )
        # 检查无效参数
        invalid_args = [arg for arg in tool_call.arguments if arg not in properties]
        if invalid_args:
            # 记录警告日志
            logger.warning(
                f"Tool '{given_tool_name}' received invalid arguments: {', '.join(invalid_args)}. "
                f"Valid arguments are: {', '.join(properties.keys())}"
            )
            valid_arguments = {k: v for k, v in tool_call.arguments.items() if k in properties}
            return valid_arguments

        return tool_call.arguments

    def validate_tool(
        self,
        tool_call: ToolCalling,
        original_tools: List[Tool],
        default_args: Optional[Dict[str, Any]] = None
    ):
        self._init_tools(original_tools)
        tool_name = self._check_tool_name(tool_call)
        tool_call.name = tool_name
        if isinstance(tool_call.arguments, dict):
            if default_args and isinstance(default_args, dict):
                tool_call.arguments.update(default_args)
        tool_arguments = self._check_tool_arguments(tool_call, tool_name)
        tool_call.arguments = tool_arguments