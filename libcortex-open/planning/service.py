#!/usr/bin/env python3

__author__ = "xi"
__all__ = [
    "PlanningServiceConfig",
    "PlanningService",
]

import json
import os.path
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, Iterable, List, Optional, Union

import jinja2
import rich
from agent_types.common import GenerationOptions, LLMConfig, Plan, SystemProfile, Tool, ToolCalling
from agent_types.planning import PlanningRequest, PlanningResponse
from libdata.config import Config
from libentry.mcp import api
from liblogging import log_request, logger
from pydantic import BaseModel, Field, model_validator

from .llm import LLMResponse, call_llm

__dir__ = os.path.dirname(os.path.abspath(__file__))

DEFAULT_SYSTEM_PROFILE = SystemProfile(
    description="你是一个专业的智能助手，能够理解用户需求并提供合适的解决方案",
    language="中文",
    capabilities=[
        "理解用户意图",
        "分析需求",
        "提供专业建议"
    ],
    constrains=[
        "需要充分了解用户需求",
        "提供准确和有帮助的信息"
    ]
)


class PlanningServiceConfig(BaseModel):
    """Planning service config object"""

    config_url: str = Field(
        title="全局配置URL",
        description="全局配置URL，可以是yml文件或mongodb表或配置服务。"
    )
    llm_name: Optional[str] = Field(
        title="大模型名称",
        description="从全局配置中获取生成选项大模型名称",
        default=None
    )
    llm_config: Optional[LLMConfig] = Field(default=None)
    generation_options_name: Optional[str] = Field(default=None)
    generation_options: Optional[GenerationOptions] = Field(default=None)
    system_template_path: str = Field(
        title="系统提示词模板文件路径",
        description="系统提示词模板文件路径，jinja2格式",
        default=os.path.join(__dir__, "template/system.j2")
    )
    user_template_path: str = Field(
        title="用户提示词模板文件路径",
        description="用户提示词模板文件路径，jinja2格式",
        default=os.path.join(__dir__, "template/user.j2")
    )

    @model_validator(mode="after")
    def check_configs(self):
        if self.llm_config is None and self.llm_name is None:
            raise ValueError("At least one of `llm_name` and `llm_config` should be given.")

        if self.generation_options is None and self.generation_options_name is None:
            self.generation_options = GenerationOptions()
        return self


class PlanningService:

    def __init__(self, config: PlanningServiceConfig):
        self.config = config
        self.global_config = Config.from_url(self.config.config_url)

        # For thread-safety, we use jinja2.Environment to cache templates.
        template_dict = {}
        with open(self.config.system_template_path, "r") as f:
            template_dict["system"] = f.read().strip()
        with open(self.config.user_template_path, "r") as f:
            template_dict["user"] = f.read().strip()
        self.template_env = jinja2.Environment(loader=jinja2.DictLoader(template_dict))

        logger.info(f"Using {self.get_llm_config()}")
        logger.info(f"Using {self.get_generation_options()}")

    def get_llm_config(self) -> LLMConfig:
        return (
            self.config.llm_config
            if self.config.llm_config else
            LLMConfig.model_validate(self.global_config[self.config.llm_name])
        )

    def get_generation_options(self) -> GenerationOptions:
        return (
            self.config.generation_options
            if self.config.generation_options else
            GenerationOptions.model_validate(self.global_config[self.config.generation_options_name])
        )

    @api.post(PlanningRequest.get_request_path())
    @log_request("trace_id", message_source="planning")
    def plan(self, request: PlanningRequest) -> Union[
        PlanningResponse, Generator[PlanningResponse, None, PlanningResponse]]:
        logger.info(f"Received request: {request.model_dump(exclude_none=True)}")
        messages = self._create_messages(request)
        tools = self._create_tools(request)

        if request.stream:
            return self._stream_plan(request, messages, tools)
        else:
            return self._non_stream_plan(request, messages, tools)

    def _non_stream_plan(
            self,
            request: PlanningRequest,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]]
    ) -> PlanningResponse:
        """非流式规划"""
        llm_config = self.get_llm_config()
        options = self.get_generation_options()

        kwargs: Dict[str, Any] = {
            "temperature": options.temperature
        }
        if options.stop_token_ids:
            kwargs["extra_body"] = {"stop_token_ids": options.stop_token_ids}

        logger.info(
            f"Using LLM: {llm_config.model}. "
            f"Calling LLM with: {kwargs}. "
            f"Messages: {messages}. "
            f"Tools: {tools}"
        )

        llm_response = call_llm(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            model=llm_config.model,
            messages=messages,
            tools=tools,
            stream=False,
            **kwargs
        )

        # 处理工具调用并添加默认参数
        tool_callings = []
        if llm_response.tool_callings:
            tool_callings = self._add_default_args(llm_response.tool_callings, request)

        response = PlanningResponse(
            thinking=llm_response.thinking,
            plans=Plan(
                tool_callings=tool_callings,
                content=llm_response.content,
            ),
            finished=len(tool_callings) == 0
        )
        logger.info(f"Response: {response.model_dump(exclude_none=True)}")
        return response

    def _stream_plan(
            self,
            request: PlanningRequest,
            messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]]
    ) -> Generator[PlanningResponse, None, PlanningResponse]:
        """流式规划"""
        llm_config = self.get_llm_config()
        options = self.get_generation_options()

        kwargs: Dict[str, Any] = {
            "temperature": options.temperature
        }
        if options.stop_token_ids:
            kwargs["extra_body"] = {"stop_token_ids": options.stop_token_ids}

        logger.info(
            f"Using LLM: {llm_config.model}. "
            f"Calling LLM with: {kwargs}. "
            f"Messages: {messages}. "
            f"Tools: {tools}"
        )

        llm_response_stream = call_llm(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            model=llm_config.model,
            messages=messages,
            tools=tools,
            stream=True,
            **kwargs
        )
        assert isinstance(llm_response_stream, Iterable)

        it = iter(llm_response_stream)
        try:
            while True:
                llm_response = next(it)
                assert isinstance(llm_response, LLMResponse)

                processed_tool_callings = []
                if llm_response.tool_callings:
                    processed_tool_callings = self._add_default_args(
                        llm_response.tool_callings,
                        request
                    )

                if llm_response.thinking or llm_response.content or processed_tool_callings:
                    yield PlanningResponse(
                        plans=Plan(
                            tool_callings=processed_tool_callings,
                            content=llm_response.content,
                        ),
                        finished=False,
                        thinking=llm_response.thinking
                    )
        except StopIteration as e:
            full_response = e.value
            assert isinstance(full_response, LLMResponse)

            yield PlanningResponse(
                finished=full_response.tool_callings is None or len(full_response.tool_callings) == 0
            )

            response = PlanningResponse(
                thinking=full_response.thinking,
                plans=Plan(
                    tool_callings=full_response.tool_callings,
                    content=full_response.content,
                ),
                finished=full_response.tool_callings is None or len(full_response.tool_callings) == 0
            )
            logger.info(f"Response: {response.model_dump(exclude_none=True)}")
            return response

    def _create_messages(self, request: PlanningRequest) -> List[Dict[str, Any]]:
        """创建消息列表"""

        messages = list()

        messages.append({
            "role": "system",
            "content": self._make_system_prompt(request)
        })

        # todo: print for debug
        rich.print("[bold red]System Prompt[/bold red]")
        print(messages[-1]["content"])
        rich.print("[bold red]" + "*" * 20 + "[/bold red]")

        session_memory = request.session_memory
        if session_memory and session_memory.chat_history:
            for message in session_memory.chat_history:
                if message.role in {"user", "assistant"}:
                    messages.append({
                        "role": message.role,
                        "content": message.content
                    })

        messages.append({
            "role": "user",
            "content": self._make_user_prompt(request)
        })

        # todo: print for debug
        rich.print("[bold blue]User Prompt[/bold blue]")
        print(messages[-1]["content"])
        rich.print("[bold blue]" + "*" * 20 + "[/bold blue]")

        if request.observations:
            for obs in request.observations:
                plan = obs.plan
                m: Dict = {"role": "assistant"}
                messages.append(m)

                calling_list = plan.tool_callings
                if calling_list:
                    tool_calls = []
                    m["tool_calls"] = tool_calls
                    for calling in calling_list:
                        # 去除default_args的字段再输入给llm, 避免上下文过长
                        arguments = calling.arguments.copy()
                        if request.default_args:
                            for key in request.default_args:
                                if key in arguments:
                                    arguments.pop(key, None)

                        tool_calls.append({
                            "id": str(uuid.uuid4()),
                            "type": "function",
                            "function": {
                                "name": calling.name,
                                "arguments": json.dumps(arguments, ensure_ascii=False)
                            }
                        })

                    status_list = obs.status
                    ignored_fields = set(request.ignored_results) if request.ignored_results else None
                    for call, status in zip(tool_calls, status_list):
                        content = status.result or f"Error: {status.error.message}"
                        if isinstance(content, (Dict, List)):
                            if ignored_fields and isinstance(content, Dict):
                                content = {
                                    k: v for k, v in content.items()
                                    if k not in ignored_fields
                                }
                            content = json.dumps(content, ensure_ascii=False)
                        if not isinstance(content, str):
                            content = str(content)
                        messages.append({
                            "role": "tool",
                            "content": content,
                            "tool_call_id": call["id"]
                        })
                else:
                    if plan.content:
                        m["content"] = plan.content

        if not request.enable_thinking:
            messages[-1]['content'] += ' /no_think'

        return messages

    def _make_system_prompt(self, request: PlanningRequest) -> str:
        session_memory = request.session_memory
        if session_memory and session_memory.chat_history:
            for message in session_memory.chat_history:
                if message.role == "system":
                    return message.content

        system_profile = request.system_profile or DEFAULT_SYSTEM_PROFILE

        now = datetime.now()
        date = now.strftime("%Y年%m月%d日")
        # time = now.strftime("%H:%M:%S")
        domain_knowledge = [
            f"今天的日期是{date}。"
        ]
        system_memory = request.system_memory
        if system_memory and system_memory.domain_knowledge:
            domain_knowledge += [*filter(
                lambda item: item,
                map(
                    lambda item: item.strip(),
                    system_memory.domain_knowledge
                )
            )]
        return self.template_env.get_template("system").render(
            system_profile=system_profile,
            domain_knowledge=domain_knowledge
        )

    def _make_user_prompt(self, request: PlanningRequest) -> str:
        mentions = None
        session_memory = request.session_memory
        if session_memory and session_memory.mentions:
            mentions = [*filter(
                lambda item: item.name and item.content,
                session_memory.mentions
            )]
        return self.template_env.get_template("user").render(
            task=request.task,
            mentions=mentions
        )

    def _create_tools(self, request: PlanningRequest) -> List[Dict[str, Any]]:
        """创建工具列表"""

        result = []
        for tool in request.tools:
            tool_dict: Dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                }
            }
            result.append(tool_dict)
            if tool.input_schema:
                tool_dict["function"]["parameters"] = tool.input_schema.model_dump(exclude_none=True)

                if request.default_args:
                    params = tool_dict["function"]["parameters"]

                    for param in request.default_args:
                        if param in params["properties"]:
                            params["properties"].pop(param, None)

                        if "required" in params and param in params["required"]:
                            params["required"].remove(param)

        return result

    def _add_default_args(self, tool_callings: List[ToolCalling], request: PlanningRequest) -> List[ToolCalling]:
        """为工具调用添加默认参数"""
        if not request.default_args:
            return tool_callings

        tool_map: Dict[str, Tool] = {
            tool.name: tool
            for tool in request.tools
        }

        result_tool_callings = []
        for tool_calling in tool_callings:
            # 复制工具调用
            new_arguments = tool_calling.arguments.copy()

            # 添加默认参数
            if tool_calling.name in tool_map:
                original_arguments = tool_map[tool_calling.name].input_schema.properties
                for arg_name, arg_value in request.default_args.items():
                    if arg_name in original_arguments:
                        new_arguments[arg_name] = arg_value

            result_tool_callings.append(ToolCalling(
                name=tool_calling.name,
                arguments=new_arguments
            ))

        return result_tool_callings
