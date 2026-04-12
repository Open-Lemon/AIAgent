from typing import Dict, Union, Optional, Callable, Any
from abc import ABC, abstractmethod
from collections import OrderedDict

from pydantic import BaseModel, Field


class PromptSection(BaseModel):
    """表示提示中的一个部分"""
    key: str  # 部分键（内部标识）
    content: Union[str, Callable[[Dict], str]]  # 内容或内容生成函数
    condition: Optional[Callable[[Dict], bool]] = None  # 可选的条件函数
    position: Optional[int] = None  # 可选的位置索引（越小越靠前）


class PromptConfig(BaseModel):
    """提示构建的配置"""

    # 输入字段映射配置。A: B, A是预定义的名字，B是实际输入的Key
    field_mappings: Dict[str, str] = Field(default_factory=lambda: {
        "query": "query",
    })

    # 其他选项
    delete_other_fields: bool = True

    class Config:
        arbitrary_types_allowed = True  # 允许 Callable 类型


class BasePromptBuilder(ABC):
    """Prompt构建器的抽象基类"""
    def __init__(self, config: PromptConfig):
        self.config = config
        self.sections = OrderedDict()  # 使用有序字典维护section顺序
        self._initialize_sections()

    @abstractmethod
    def _initialize_sections(self):
        """初始化sections，子类必须实现"""
        pass

    def add_section(
        self,
        key: str,
        content: Union[str, Callable[[Dict], str]],
        condition: Optional[Callable[[Dict], bool]] = None,
        position: Optional[int] = None
    ) -> None:
        """
        添加一个新的提示部分

        Args:
            key: 部分唯一标识
            name: 显示名称
            content: 内容或内容生成函数
            condition: 显示条件函数
            position: 位置索引（None表示添加到末尾）
        """
        section = PromptSection(
            key=key,
            content=content,
            condition=condition,
            position=position
        )

        if position is not None:
            # 插入到指定位置
            items = list(self.sections.items())
            items.insert(position, (key, section))
            self.sections = OrderedDict(items)
        else:
            # 添加到末尾
            self.sections[key] = section

    def remove_section(self, key: str) -> None:
        """移除一个提示部分"""
        if key in self.sections:
            del self.sections[key]

    def build_prompt(
        self,
        input_dict: Optional[Dict] = None
    ) -> str:
        """
        构建完整的提示
        """

        # 合并sections
        sections = OrderedDict(self.sections)

        # 构建提示
        prompt_parts = []
        for section in sections.values():
            # 检查条件
            if section.condition is None or section.condition(input_dict):
                # 获取内容
                content = (
                    section.content(input_dict)
                    if callable(section.content)
                    else section.content
                )
                if content:
                    prompt_parts.append(f"{content}")

        return "\n\n".join(prompt_parts)

    def _get_mapped_field(self, field_name: str, input_dict: Dict) -> Any:
        """根据字段映射获取输入值"""
        mapped_name = self.config.field_mappings.get(field_name, field_name)
        return input_dict.get(mapped_name)
