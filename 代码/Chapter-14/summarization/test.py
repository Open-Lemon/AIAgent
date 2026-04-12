#!/usr/bin/env python3

__author__ = "xi"

from libentry.mcp.client import APIClient

from agent_types.common import ExecutionError, ExecutionStatus, Observation, Plan, SystemProfile, ToolCalling
from agent_types.summarization import SummarizationRequest, SummarizationResponse


def main():
    client = APIClient("http://localhost:25000")

    request = SummarizationRequest(
        task="北京位于哪里，热不热？",
        observations=[
            Observation(
                plan=Plan(tool_callings=[ToolCalling(name="GetLocation")]),
                status=[ExecutionStatus(name="GetLocation", result="East of China, 坐标 (100, 200)")]
            ),
            Observation(
                plan=Plan(tool_callings=[ToolCalling(name="Weather")]),
                status=[ExecutionStatus(name="Weather", result="最高气温80摄氏度，最低气温-20摄氏度，降水概率10%，大风12级")]
            ),
        ],
        stream=True,
        system_profile=SystemProfile(
            description="你是一只猫，你说话喜欢喵喵叫",
            constrains=["请使用JSON格式输出，例如{\"answer\": \"回复内容\"}"]
        )
    )
    output = client.post("/summarize", request)

    for response in output:
        response = SummarizationResponse.model_validate(response)
        print(response.content, end="", flush=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
