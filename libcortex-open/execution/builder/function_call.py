import json
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from liblogging import logger
from libentry.resource import ResourceManager
import rich

from agent_types.common import Tool, SessionMemory, SystemProfile, LLMConfig
from execution.prompt.argument_filling import ArgumentFillingUserPromptBuilder, ArgumentFillingSystemPromptBuilder
from execution.prompt.meta_prompt import PromptConfig
from execution.llm.sync_llm_client import LLMGenerationOptions, sync_request_llm
from utils.repair import structure_output_repair


class ArgumentFillerConfig(BaseModel):
    resource: str = Field(description="资源管理器，可以是本地yaml文件，或者远程管理服务地址")
    llm_name: str = Field(description="大模型的名称，从统一的资源配置中获取")
    llm_generation_options: LLMGenerationOptions = Field(default_factory=LLMGenerationOptions)
    field_mappings: Dict[str, str] = Field(default_factory=lambda: {
        "query": "query",
    })
    enabled: bool = Field(default=True, description="是否启用参数填充")


class ArgumentFiller:

    def __init__(self, config: ArgumentFillerConfig):
        self.config = config
        self.resource_manager = ResourceManager(self.config.resource)
        self.llm_config = LLMConfig.model_validate(self.resource_manager.get(self.config.llm_name))
        self.user_prompt_builder = ArgumentFillingUserPromptBuilder(
            PromptConfig.model_validate({
                "field_mappings": self.config.field_mappings
            })
        )
        self.system_prompt_builder = ArgumentFillingSystemPromptBuilder(
            PromptConfig.model_validate({
                "field_mappings": self.config.field_mappings
            })
        )

    def run(
        self,
        missing_args: List,
        tool: Tool,
        query: Optional[str] = None,
        session_memory: Optional[SessionMemory] = None,
        system_profile: Optional[SystemProfile] = None
    ) -> Dict[str, Any]:
        """
        构建user prompt时, 入参: rules为字符串, tool应该为字典, memory为字典, history为列表
        """

        properties = tool.input_schema.properties or {}
        missing_args_schema = {}
        for arg in missing_args:
            if arg in properties:
                missing_args_schema[arg] = properties[arg].model_dump(exclude_none=True)
        input_dict = {}
        info_focus_tool = {
            "name": tool.name,
            "description": tool.description,
            "parameters": missing_args_schema
        }
        input_dict["tools"] = info_focus_tool
        if query:
            input_dict["query"] = query
        if system_profile and system_profile.constrains:
            rules = "\n".join(system_profile.constrains)
            input_dict["rules"] = rules

        if session_memory:
            chat_history = session_memory.get_messages(role="user")
            history = [message.model_dump(exclude_none=True) for message in chat_history]
            input_dict["history"] = history
            if session_memory.mentions:
                mentions = [m.model_dump(exclude_none=True) for m in session_memory.mentions]
                memory_dict = {"mentions": mentions}
                input_dict["memory"] = memory_dict

        system_prompt = self.system_prompt_builder.build_prompt()
        rich.print("<system prompt>")
        rich.print(system_prompt)
        user_prompt = self.user_prompt_builder.build_prompt(input_dict)
        rich.print("<user prompt>")
        rich.print(user_prompt)
        response = sync_request_llm(
            llm_config=self.llm_config,
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            generation_config=self.config.llm_generation_options
        )
        try:
            result = structure_output_repair(response.choices[0].message.content)[0]
        except Exception as e:
            logger.error(f"结构化输出修复失败: {e}")
            logger.info({"llm_content": response.choices[0].message.content})
            result = {}
        return result
