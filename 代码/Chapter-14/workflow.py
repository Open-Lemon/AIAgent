#!/usr/bin/env python3

__author__ = "xi"

import uuid
from typing import List, Optional

import rich
from libentry import ArgumentParser
from libentry.mcp.client import APIClient
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel

from agent_types.common import Intent, Observation, Plan, SessionMemory, SystemMemory, SystemProfile, Tool
from agent_types.execution import ToolExecutingRequest, ToolExecutingResponse
from agent_types.memory.session import ReadSessionMemoryRequest, ReadSessionMemoryResponse, WriteChatHistoryRequest
from agent_types.planning import PlanningRequest, PlanningResponse
from agent_types.summarization import SummarizationRequest, SummarizationResponse

console = Console()


class Context(BaseModel):
    """Workflow context shared between nodes."""

    session_id: str = None
    turn_id: int = 1
    query: str = None
    intent: Optional[Intent] = None
    tools: List[Tool] = []
    system_profile: Optional[SystemProfile] = None
    system_memory: Optional[SystemMemory] = None
    session_memory: Optional[SessionMemory] = None
    plan: Optional[Plan] = None
    finished: bool = False
    observations: List[Observation] = []
    response: Optional[str] = None
    default_args: Optional[dict] = {}


class WorkflowConfig(BaseModel):
    session_memory_url: str
    planning_url: str
    execution_url: str
    summarization_url: str
    max_iterations: int


class Workflow:

    def __init__(self, config: WorkflowConfig):
        self.config = config

        self.session_memory = APIClient(self.config.session_memory_url)
        self.planner = APIClient(self.config.planning_url)
        self.executor = APIClient(self.config.execution_url)
        mcp_tools = self.executor.post("/list_tools", {}).get("tools")
        self.tools = []
        for tool in mcp_tools:
            self.tools.append(Tool.model_validate(tool))
        self.summarizer = APIClient(self.config.summarization_url)

        self.session_id = str(uuid.uuid4())
        self.max_iterations = self.config.max_iterations

    @staticmethod
    def _display_message(content: str, role: str):
        """格式化显示消息"""
        if role == "assistant":
            console.print(Panel(content, title="[bold green]Assistant[/bold green]", border_style="green"))
        elif role == "tool":
            console.print(Panel(content, title="[bold yellow]Tool Result[/bold yellow]", border_style="yellow"))
        elif role == "error":
            console.print(Panel(content, title="[bold red]Error[/bold red]", border_style="red"))

    def run(self):
        rich.print(self.session_id)
        while True:
            query = input("\nUser: ").strip()
            if query.lower() in ['exit', 'quit', 'bye']:
                console.print("[bold blue]Goodbye![/bold blue]")
                break
            default_args = {
                "query": query,
                "user_info": {"uid": "10216994180", "user_identity": "1"},
                "trace_id": self.session_id,
                "uid": "10216994180",
                "use_llm": True,
                "terminal": "1",
                "bind_mobile_id": ""
            }
            context = Context(
                session_id=self.session_id,
                turn_id=1,
                query=query,
                tools=self.tools,
                default_args=default_args
            )

            self.read_session_memory(context)

            # for m in context.session_memory.chat_history:
            #     rich.print(m)

            # Iterative Plan & Execute
            for i in range(self.max_iterations):
                self.plan(context)

                tool_callings = context.plan.tool_callings
                if tool_callings:
                    print("正在调用工具")
                    for calling in tool_callings:
                        rich.print(calling)

                self.execute(context)
                if context.finished:
                    break

            # Summarize
            self.summarize(context)
            self._display_message(role="assistant", content=context.response)

            # Write SessionMemory
            self.write_user_message(context)
            self.write_assistant_message(context)

    def read_session_memory(self, context: Context):
        request = ReadSessionMemoryRequest(session_id=context.session_id, n=0)
        response = self.session_memory.post("/read_session_memory", request.model_dump())
        response = ReadSessionMemoryResponse.model_validate(response)

        context.session_memory = response.session_memory

    def write_user_message(self, context: Context):
        request = WriteChatHistoryRequest(
            session_id=context.session_id,
            role="user",
            content=context.query,
        )
        self.session_memory.post("/write_chat_history", request.model_dump())

    def write_assistant_message(self, context: Context):
        request = WriteChatHistoryRequest(
            session_id=context.session_id,
            role="assistant",
            content=context.response,
        )
        self.session_memory.post("/write_chat_history", request.model_dump())

    def plan(self, context: Context):
        profile = SystemProfile(
            description="你是智能助手，具备判断是否需要调用外部工具来完成用户请求的能力。",
            language="中文",
            constrains=[
                "政治相关、危险行为等敏感话题一定要拒绝回答，此时语气要和善且坚决。",
                "尽量找合适的工具来获取信息，基于工具返回的信息回答。如果不确定使用什么工具，要大胆尝试。",
                "如果尝试多个工具都无法获取有用信息，一定不要自己尝试回答。",
                "如果工具返回的结果中包含“summary_constraints”属性，那么在最终回复的时候要按照这个属性要求的格式进行总结。",
                "[提及](#Mentions)是用户查询中提到的信息，在调用工具的时候，很多参数都会注明是用户提到的某项信息，所以你需要将#Mentions里面符合条件的内容作为工具参数"
            ]
        )
        request = PlanningRequest(
            task=context.query,
            tools=context.tools,
            intent=context.intent,
            observations=context.observations,
            session_memory=context.session_memory,
            system_profile=profile,
            default_args=context.default_args
        )
        response = self.planner.post("/plan", request.model_dump())
        response = PlanningResponse.model_validate(response)

        context.plan = response.plans
        context.finished = response.finished

    def execute(self, context: Context):
        request = ToolExecutingRequest(
            plan=context.plan,
            task=context.query,
            intent=context.intent,
            session_memory=context.session_memory,
            default_args=context.default_args
        )
        response = self.executor.post("/execute_tools", request.model_dump())
        response = ToolExecutingResponse.model_validate(response)

        context.observations.append(response.observation)

    def summarize(self, context: Context):
        profile = SystemProfile(
            description="你是一个专业且富有同理心的AI助手，擅长总结和回应用户问题。在对话中保持活泼可爱的语气，让交流更加轻松愉快",
            capabilities=[
                "准确理解上下文并提供清晰的总结回复",
                "善于营造轻松愉快的聊天氛围，能够自然地进行日常交谈",
                "当用户表述不明确时，能够礼貌地请求澄清或提供引导性问题",
                "在无法完全满足用户需求时，提供替代方案或委婉解释",
                "具备基本的情感识别能力，能对用户的情绪做出恰当回应"
            ],
            constrains=[
                "不输出涉及暴力、色情的内容",
                "不违反法律法规",
                "不传播虚假或具有误导性的信息",
                "保护用户隐私，不收集或泄露个人敏感信息"
            ]
        )
        request = SummarizationRequest(
            task=context.query,
            observations=context.observations,
            session_memory=context.session_memory,
            system_profile=profile
        )

        result = self.summarizer.post("/summarize", request.model_dump())
        result = SummarizationResponse.model_validate(result)
        context.response = result.content


def main():
    parser = ArgumentParser()
    parser.add_schema("config", WorkflowConfig)
    args = parser.parse_args()

    workflow = Workflow(args.config)
    workflow.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
