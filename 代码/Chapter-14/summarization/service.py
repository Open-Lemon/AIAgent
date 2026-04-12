#!/usr/bin/env python3

__author__ = "xi"

import json
import os.path
from typing import Dict, Generator, List, Optional, Union

import jinja2
import rich
from agent_types.common import GenerationOptions, LLMConfig, ToolResponse
from agent_types.summarization import SummarizationRequest, SummarizationResponse
from libdata.config import Config
from libentry import logger
from libentry.mcp import api
from pydantic import BaseModel, Field, ValidationError

from summarization.llm import LLMResponse, call_llm

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "template")


class SummarizationConfig(BaseModel):
    """总结模块配置信息"""

    config_url: str = Field(
        title="全局配置URL",
        description="全局配置URL，可以是yml文件或mongodb表或配置服务。"
    )
    llm_name: Optional[str] = Field(
        title="大模型配置项名称",
        description="大模型配置项名称",
        default=None
    )
    generation_options_name: Optional[str] = Field(
        title="生成选项配置项名称",
        description="生成选项配置项名称",
        default=None
    )
    llm: Optional[LLMConfig] = Field(
        title="大模型配置",
        description="大模型配置",
        default=None
    )
    generation_options: Optional[GenerationOptions] = Field(
        title="生成选项",
        description="生成选项",
        default=None
    )
    system_template_path: str = Field(
        title="系统提示模板",
        description="系统提示模板",
        default=os.path.join(TEMPLATE_DIR, "system.j2")
    )
    user_template_path: str = Field(
        title="用户提示模板",
        description="用户提示模板",
        default=os.path.join(TEMPLATE_DIR, "user.j2")
    )


class SummarizationService:

    def __init__(self, config: SummarizationConfig):
        self.config = config

        # For thread-safety, we use jinja2.Environment to cache templates.
        template_dict = {}
        with open(self.config.system_template_path, "r") as f:
            template_dict["system"] = f.read().strip()
        with open(self.config.user_template_path, "r") as f:
            template_dict["user"] = f.read().strip()
        self.template_env = jinja2.Environment(
            loader=jinja2.DictLoader(template_dict),
            trim_blocks=True,
            lstrip_blocks=True
        )

        self.global_config = Config.from_url(self.config.config_url)
        logger.info(f"Using {self.get_llm_config()}")
        logger.info(f"Using {self.get_generation_options()}")

    def get_llm_config(self) -> LLMConfig:
        if self.config.llm_name is not None:
            return LLMConfig.model_validate(self.global_config.get(self.config.llm_name))
        elif self.config.llm is not None:
            return self.config.llm
        else:
            options = self.get_generation_options()
            if options.model_name is not None:
                return LLMConfig.model_validate(self.global_config.get(options.model_name))
            else:
                raise ValueError("Cannot find LLM config.")

    def get_generation_options(self) -> GenerationOptions:
        if self.config.generation_options_name is not None:
            return GenerationOptions.model_validate(
                self.global_config.get(self.config.generation_options_name)
            )
        elif self.config.generation_options is not None:
            return self.config.generation_options
        else:
            raise ValueError("Cannot find generation options.")

    @api.post(SummarizationRequest.get_request_path())
    def summarize(
            self,
            request: SummarizationRequest
    ) -> Union[SummarizationResponse, Generator[SummarizationResponse, None, Optional[SummarizationResponse]]]:
        merged_metadata = {}
        if request.observations:
            i = 0
            for o in request.observations:
                calling_list = o.plan.tool_callings
                status_list = o.status
                if not (calling_list and status_list):
                    continue
                for calling, status in zip(calling_list, status_list):
                    i += 1
                    try:
                        tool_response = ToolResponse.model_validate(status.result)
                        if tool_response.metadata:
                            merged_metadata[f"{i}:{calling.name}"] = tool_response.metadata
                    except ValidationError:
                        continue
        if not merged_metadata:
            merged_metadata = None

        messages = self._create_messages(request)

        options = self.get_generation_options()
        if request.generation_options is not None:
            options = request.generation_options
        # todo: 目前即使在request.generation_options中指定了model_name，也不会生效
        llm_config = self.get_llm_config()
        extra_body: dict = {
            "chat_template_kwargs": {
                "enable_thinking": request.enable_thinking
            }
        }
        if options.stop_token_ids:
            extra_body["stop_token_ids"] = options.stop_token_ids
        response = call_llm(
            base_url=llm_config.base_url,
            api_key=llm_config.api_key,
            model=llm_config.model,
            messages=messages,
            tools=[],
            stream=request.stream,
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            extra_body=extra_body
        )

        if not request.stream:
            assert isinstance(response, LLMResponse)
            return SummarizationResponse(
                trace_id=request.trace_id,
                content=response.content,
                thinking=response.thinking if request.enable_thinking else None,
                metadata=merged_metadata if merged_metadata else None
            )
        else:
            return self._iter_response(response, request, merged_metadata)

    def _iter_response(
            self,
            response: LLMResponse,
            request: SummarizationRequest,
            merged_metadata: Optional[Dict]
    ) -> Generator[SummarizationResponse, None, Optional[SummarizationResponse]]:
        it = iter(response)
        i = 0
        try:
            while True:
                chunk = next(it)
                assert isinstance(chunk, LLMResponse)
                content = chunk.content
                thinking = chunk.thinking if request.enable_thinking else None
                metadata = merged_metadata if i == 0 else None
                i += 1
                if content is not None or thinking is not None or metadata is not None:
                    yield SummarizationResponse(
                        trace_id=request.trace_id,
                        content=content,
                        thinking=thinking,
                        metadata=metadata
                    )
        except StopIteration as e:
            full = e.value
            if full is not None:
                assert isinstance(full, LLMResponse)
                return SummarizationResponse(
                    trace_id=request.trace_id,
                    content=full.content,
                    thinking=full.thinking if request.enable_thinking else None,
                    metadata=merged_metadata
                )
        return None

    def _create_messages(self, request: SummarizationRequest) -> List[Dict]:
        messages = list()

        # system prompt
        kwargs = {}
        if request.system_profile is not None:
            kwargs = request.system_profile.model_dump()
        system_prompt = self.template_env.get_template("system").render(**kwargs)
        messages.append({"role": "system", "content": system_prompt})
        # todo: print for debug
        rich.print(f"[bold red]System Prompt\n{system_prompt}\n[/bold red]")

        # chat history
        session_memory = request.session_memory
        if session_memory and session_memory.chat_history:
            for m in session_memory.chat_history:
                if m.role in {"user", "assistant"}:
                    messages.append({"role": m.role, "content": m.content})

        # user prompt
        converted_observations = self._convert_observations(request)
        user_prompt = self.template_env.get_template("user").render(
            query=request.task,
            intent=request.intent,
            observations=converted_observations
        )
        if not request.enable_thinking:
            user_prompt = user_prompt + "/no_think"
        messages.append({"role": "user", "content": user_prompt})
        # todo: print for debug
        rich.print(f"[bold blue]User Prompt\n{user_prompt}\n[/bold blue]")

        return messages

    def _convert_observations(self, request: SummarizationRequest) -> List[Dict]:
        converted_observations = []
        conclusion = None

        observations = request.observations
        for obs in observations:
            calling_list = obs.plan.tool_callings
            status_list = obs.status
            assert len(calling_list) == len(status_list)

            for calling, status in zip(calling_list, status_list):
                result = None
                summary_constraints = []
                if isinstance(status.result, Dict):
                    try:
                        tool_response = ToolResponse.model_validate(status.result)
                        # todo: 需要基于tool_response.skip_summarize跳过总结
                        result = tool_response.response_text
                        if tool_response.summary_constraints:
                            for line in tool_response.summary_constraints:
                                line = self._remove_blank_lines(line)
                                summary_constraints.append(line)
                        if not result:
                            # todo: 这是个临时补丁！！
                            result = {**status.result}
                            if "summary_constraints" in result:
                                del result["summary_constraints"]
                            if "metadata" in result:
                                del result["metadata"]
                            result = json.dumps(result, ensure_ascii=False)
                    except ValidationError:
                        pass

                if result is None:
                    result = json.dumps(status.model_dump(exclude_none=True), ensure_ascii=False)

                converted_observations.append({
                    "calling": calling.name,
                    "result": self._remove_blank_lines(result),
                    "summary_constraints": summary_constraints
                })

            if len(calling_list) == 0 and obs.plan.content:
                conclusion = {
                    "result": self._remove_blank_lines(obs.plan.content)
                }
        if not converted_observations:
            if conclusion:
                converted_observations.append(conclusion)

        return converted_observations

    @staticmethod
    def _remove_blank_lines(content: str) -> str:
        return "\n".join(line.rstrip() for line in content.split("\n") if line.strip())
