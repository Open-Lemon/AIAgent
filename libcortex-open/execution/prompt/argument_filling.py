import json
from typing import Dict, List, Union

import yaml

from .meta_prompt import BasePromptBuilder, PromptConfig


USER_INSTRUCTION_PATH = "execution/prompt/argument_filling/user.yaml"
SYSTEM_INSTRUCTION_PATH = "execution/prompt/argument_filling/system.yaml"


class ArgumentFillingSystemPromptBuilder(BasePromptBuilder):
    def __init__(self, config: PromptConfig = PromptConfig()):
        with open(SYSTEM_INSTRUCTION_PATH, "r", encoding="utf-8") as f:
            self.instruction_dict = yaml.safe_load(f)
        super().__init__(config)

    def _initialize_sections(self):
        """初始化默认的提示部分"""
        self.add_section(
            key="system",
            content=self.instruction_dict["system"]
        )


class ArgumentFillingUserPromptBuilder(BasePromptBuilder):
    """通用的Meta Prompt构建器"""
    def __init__(self, config: PromptConfig = PromptConfig()):
        with open(USER_INSTRUCTION_PATH, "r", encoding="utf-8") as f:
            self.instruction_dict = yaml.safe_load(f)
        super().__init__(config)

    def _initialize_sections(self):
        """初始化默认的提示部分"""
        # 按顺序添加默认sections
        self.add_section(
            key="task",
            content=self.instruction_dict["task"]
        )
        self.add_section(
            key="tools",
            content=self._format_tools,
            condition=lambda d: bool(self._get_mapped_field("tools", d))
        )
        self.add_section(
            key="output_format",
            content=self.instruction_dict["output_format"],
        )

        self.add_section(
            key="rules",
            content=self._format_rules,
            condition=lambda d: bool(self._get_mapped_field("rules", d))
        )

        self.add_section(
            key="memory",
            content=self._format_memory,
            condition=lambda d: bool(self._get_mapped_field("memory", d))
        )

        self.add_section(
            key="history",
            content=self._format_history,
            condition=lambda d: bool(self._get_mapped_field("history", d))
        )

        self.add_section(
            key="query",
            content=self._format_query
        )

    def _format_tools(self, input_dict: Dict) -> str:
        """格式化工具部分, tools应该为字典"""
        tools = self._get_mapped_field("tools", input_dict)
        return self.instruction_dict["tools"].format_map(
            {"tool_schema": json.dumps(tools, ensure_ascii=False, indent=4)}
        )

    def _format_rules(self, input_dict: Dict) -> str:
        """格式化规则部分, rules应该为字符串"""
        rules = self._get_mapped_field("rules", input_dict)
        return self.instruction_dict["rules"].format_map(
            {"rules": rules}
        )

    def _format_memory(self, input_dict: Dict) -> str:
        """格式化记忆部分, memory是字典"""
        memory = self._get_mapped_field("memory", input_dict)
        return self.instruction_dict["memory"].format_map(
            {"memory_dict": json.dumps(memory, ensure_ascii=False, indent=4)}
        )

    def _build_chat_history(
        self,
        history: Union[str, List[Dict]]
    ) -> str:
        """构建聊天历史记录"""
        history_instruction = self.instruction_dict["history"]
        if isinstance(history, str):
            return history_instruction.format_map({"history_list": history})

        history_list = []
        for _, turn in enumerate(history):
            if isinstance(turn, dict):
                role = turn.get("role", "")
                content = turn.get("content", "")
                history_list.append({"role": role, "content": content})
            else:
                raise ValueError(f"{turn} must be dict. now it is {type(turn)}")
        return history_instruction.format_map(
            {"history_list": json.dumps(history_list, indent=4, ensure_ascii=False)}
        )

    def _format_history(self, input_dict: Dict) -> str:
        """格式化历史记录部分"""
        history = self._get_mapped_field("history", input_dict)
        return self._build_chat_history(
            history=history
        )

    def _format_query(self, input_dict: Dict) -> str:
        """格式化输入参数部分"""
        query_instruction = self.instruction_dict["query"]
        query_value = self._get_mapped_field("query", input_dict)
        predefined_fields = self.sections.keys()
        if self.config.delete_other_fields:
            # 空字典
            output_dict = {}
        else:
            # 复制输入字典并删除查询字段
            output_dict = input_dict.copy()
            output_dict.pop(self.config.field_mappings["query"])

        final_dict = {"query": query_value}
        for key, value in output_dict.items():
            if key != "query" and key not in predefined_fields:
                final_dict[key] = value
        return query_instruction.format_map({
            "query_dict": json.dumps(final_dict, indent=4, ensure_ascii=False)
        })
