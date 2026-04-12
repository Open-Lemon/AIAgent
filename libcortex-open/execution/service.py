import json
from typing import Any, Dict, Optional

import rich
from libentry.mcp import api
from pydantic import BaseModel, Field
from liblogging import logger, log_request

from agent_types.common import ExecutionStatus, ExecutionError, ToolCalling, Observation, Plan
from agent_types.execution import ToolExecutingRequest, ToolExecutingResponse
from agent_types.execution import ListToolsRequest, ListToolsResponse
from execution.builder.tool_checker import ToolChecker, ToolCheckerConfig, WrongToolNameError, MissRequiredArgumentError
from execution.builder.mcp_client import build_mcp_client
from execution.builder.function_call import ArgumentFiller, ArgumentFillerConfig


class ToolExecutorConfig(BaseModel):
    tool_checker_config: ToolCheckerConfig = Field(default_factory=ToolCheckerConfig)
    argument_filler_config: ArgumentFillerConfig
    mcp_server_config_path: str = Field(
        title="MCP Server Config Path",
        description="The path to the MCP server configuration file",
        default="execution/config/lenovo_mcp_server.json"
    )
    max_retry_times: int = Field(
        title="最大重试次数",
        description="工具执行失败时，最大重试次数",
        default=2
    )


class ToolExecutor:

    def __init__(self, config: ToolExecutorConfig):
        self.config = config
        rich.print(config)
        self.tool_checker = ToolChecker(config.tool_checker_config)
        self.error_fixer = None  # TODO: Error repair logic
        self.function_caller = ArgumentFiller(config.argument_filler_config)
        with open(self.config.mcp_server_config_path, "r") as f:
            self.mcp_server_config = json.load(f).get("mcpServers", {})
        rich.print(f"Loaded MCP server config: {self.mcp_server_config}")
        self.client_pool = build_mcp_client(self.mcp_server_config)
        self.name2server: Dict[str, str] = {}
        self.all_tools = self.list_tools().tools

    @api.route()
    @log_request("trace_id", message_source="execution")
    def execute_tools(self, request: ToolExecutingRequest) -> ToolExecutingResponse:
        """
        执行工具
        """
        logger.info(f"Received request: {request.model_dump(exclude_none=True)}")
        status_list = []
        tool_callings = request.plan.tool_callings

        for tool_call in tool_callings:
            es = self._execute_single_tool(tool_call, request)
            status_list.append(es)
        logger.info(f"Execution status: {status_list}")
        return ToolExecutingResponse(
            observation=Observation(plan=request.plan, status=status_list)
        )

    def _execute_single_tool(self, tool_call: ToolCalling, request_context: ToolExecutingRequest) -> ExecutionStatus:
        retry_times = 0

        while retry_times < self.config.max_retry_times:
            try:
                self._prepare_tool_call(tool_call, request_context.default_args)
                result = self._execute_tool_call(tool_call)
                return self._build_execution_status(tool_call.name, result=result)

            except WrongToolNameError as e:
                return self._build_execution_status(tool_call.name, error=e)

            except MissRequiredArgumentError as e:
                if not self.config.argument_filler_config.enabled:
                    return self._build_execution_status(tool_call.name, error=e)
                else:
                    filled = self._handle_missing_arguments(e, tool_call, request_context)
                    logger.info(filled)
                    if filled:
                        tool_call.arguments.update(filled)
                        retry_times += 1
                        continue
                    else:
                        return self._build_execution_status(tool_call.name, error=e)

            except Exception as e:
                return self._build_execution_status(tool_call.name, error=e)

        # Max retries exceeded
        return ExecutionStatus(
            name=tool_call.name,
            error=ExecutionError(
                error="MaxRetryError",
                message=f"Reached maximum retry times ({self.config.max_retry_times})."
            )
        )

    def _prepare_tool_call(self, tool_call: ToolCalling, default_args: Optional[Dict[str, Any]] = None):
        """验证工具名称和参数"""
        self.tool_checker.validate_tool(tool_call, self.all_tools, default_args=default_args)

    def _execute_tool_call(self, tool_call: ToolCalling):
        """执行具体的工具调用"""
        server_name = self.name2server.get(tool_call.name)
        client = self.client_pool[server_name]
        config = self.mcp_server_config.get(server_name)

        if config.get("type") == "libentry":
            result = client.call(tool_call.name, tool_call.arguments)
        else:
            endpoint = config.get("endpoint")
            with client.start_session(sse_endpoint=endpoint) as session:
                session.initialize()
                result = session.call_tool(tool_call.name, tool_call.arguments)
        return result

    def _handle_missing_arguments(
            self,
            error: MissRequiredArgumentError,
            tool_call: ToolCalling,
            request_context: ToolExecutingRequest
    ):
        """尝试填充缺失的参数"""
        matched_tool = next((t for t in self.all_tools if t.name == tool_call.name), None)
        missing_args = error.missing_args
        try:
            result = self.function_caller.run(
                query=request_context.task,
                missing_args=missing_args,
                tool=matched_tool,
                session_memory=request_context.session_memory,
                system_profile=request_context.system_profile
            )
            return result
        except Exception as internal_error:
            rich.print(internal_error)
            return None

    def _build_execution_status(self, tool_name: str, result=None, error=None):
        """构造执行状态对象"""
        if error:
            return ExecutionStatus(
                name=tool_name,
                error=ExecutionError(error=str(type(error)), message=str(error))
            )
        else:
            return ExecutionStatus(name=tool_name, result=result)

    @api.route()
    def list_tools(self, request: ListToolsRequest = None) -> ListToolsResponse:
        """
        列出工具，并构建工具名到服务器的映射
        """
        all_tools = []
        for server_name, config in self.mcp_server_config.items():
            if not config.get("enabled"):
                continue
            client = self.client_pool[server_name]

            try:
                if config.get("type") == "libentry":
                    tools = client.list_tools().tools
                else:
                    client = self.client_pool[server_name]
                    endpoint = config.get("endpoint")
                    with client.start_session(sse_endpoint=endpoint) as session:
                        session.initialize()
                        tools = session.list_tools().tools

                for tool in tools:
                    self.name2server[tool.name] = server_name

                all_tools.extend(tools)
            except Exception as e:
                rich.print(f"[red]Error listing tools for {server_name}: {str(e)}[/red]")
                continue

        output_tool_list = []
        for tool in all_tools:
            tool_dict = tool.model_dump()
            if 'inputSchema' in tool_dict:
                tool_dict['input_schema'] = tool_dict.pop('inputSchema')
            output_tool_list.append(tool_dict)

        return ListToolsResponse(tools=output_tool_list)
