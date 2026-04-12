from libentry.mcp import api
from libentry.mcp.service import run_service
from pydantic import BaseModel, Field


class ChitchatInput(BaseModel):
    query: str = Field(
        default="",
        description="用户的输入消息。",
    )


class ClarificationInput(BaseModel):
    tool_name: str = Field(
        ...,
        description="需要澄清的工具名称, 比如: search",
    )
    missing_params: list[str] = Field(
        ...,
        description='缺失的参数列表, 比如: ["query", "limit"]',
    )


class DefaultMockTool():

    @api.tool()
    def chitchat(self, params: ChitchatInput) -> str:
        """与用户进行闲聊对话的工具。当用户输入与其他工具无关的闲聊内容时，使用此工具进行回应。"""
        return f"可以聊聊'{params.query}'"

    @api.tool()
    def clarification(self, params: ClarificationInput) -> str:
        """当工具调用缺少必要参数时进行参数澄清。用于提示用户提供工具调用所需的必要参数信息。"""
        params_str = "\n".join([f"- {param}" for param in params.missing_params])
        return f"请为工具 '{params.tool_name}' 提供以下必要的参数信息:\n{params_str}"


if __name__ == "__main__":
    run_service(
        DefaultMockTool,
        host="0.0.0.0",
        port=19001
    )