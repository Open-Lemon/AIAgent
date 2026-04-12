#!/usr/bin/env python3

__author__ = "xi"
__all__ = [
    "LLMResponse",
    "call_llm",
]

import json
from typing import Any, Dict, Generator, Iterable, List, Optional, Union

import httpx
import openai
from agent_types.common import ToolCalling
from openai.types.chat import ChatCompletion, ChatCompletionChunk
from pydantic import BaseModel


class LLMResponse(BaseModel):
    content: Optional[str] = None
    thinking: Optional[str] = None
    tool_callings: Optional[List[ToolCalling]] = None


def call_llm(
        base_url: str,
        api_key: Optional[str],
        model: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs
) -> Union[LLMResponse, Iterable[LLMResponse]]:
    """统一的LLM调用方法，支持流式和非流式"""
    kwargs["model"] = model
    kwargs["stream"] = stream
    kwargs["messages"] = messages
    if tools:
        kwargs["tools"] = tools

    client = openai.OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=httpx.Client(verify=False)
    )
    response = client.chat.completions.create(**kwargs)

    if not stream:
        try:
            assert isinstance(response, ChatCompletion)
            if not response.choices:
                raise RuntimeError(
                    f"非常抱歉，本模型可能由于以下原因，导致无法正常服务\n"
                    f"{str(response)}"
                )
            message = response.choices[0].message

            thinking = None
            if hasattr(message, "reasoning_content"):
                thinking = getattr(message, "reasoning_content")

            tool_callings = None
            if message.tool_calls:
                tool_callings = []
                for call in message.tool_calls:
                    name = call.function.name
                    args = call.function.arguments
                    assert isinstance(args, str)
                    tool_callings.append(ToolCalling(
                        name=name,
                        arguments=json.loads(args) if args else {}
                    ))

            return LLMResponse(
                content=message.content,
                thinking=thinking,
                tool_callings=tool_callings
            )
        finally:
            client.close()
    else:
        return _iter_chunks(response, client)


def _iter_chunks(
        response: Iterable[ChatCompletionChunk],
        client
) -> Generator[LLMResponse, None, LLMResponse]:
    try:
        full_content = []
        full_thinking = []
        full_tool_callings = []

        pending_index = None
        pending_name = None
        pending_args = None
        for chunk in response:
            assert isinstance(chunk, ChatCompletionChunk)
            if not chunk.choices:
                raise RuntimeError(
                    f"非常抱歉，本模型可能由于以下原因，导致无法正常服务\n"
                    f"{str(response)}"
                )
            delta = chunk.choices[0].delta

            content = delta.content
            if content is not None:
                full_content.append(content)

            thinking = None
            if hasattr(delta, "reasoning_content"):
                thinking = getattr(delta, "reasoning_content")
            if thinking is not None:
                full_thinking.append(thinking)

            tool_callings = []
            if delta.tool_calls:
                for call in delta.tool_calls:
                    delta_index = call.index
                    delta_name = call.function.name
                    delta_args = call.function.arguments
                    if pending_index is None:
                        pending_index = delta_index
                        pending_name = delta_name
                        pending_args = delta_args
                    elif pending_index == call.index:
                        if delta_name is not None:
                            pending_name = pending_name + delta_name if pending_name else delta_name
                        if delta_args is not None:
                            pending_args = pending_args + delta_args if pending_args else delta_args
                    else:
                        tool_calling = ToolCalling(
                            name=pending_name,
                            arguments=json.loads(pending_args) if pending_args else {}
                        )
                        full_tool_callings.append(tool_calling)
                        tool_callings.append(tool_calling)
                        pending_index = delta_index
                        pending_name = delta_name
                        pending_args = delta_args

            if (content is not None) or (thinking is not None) or tool_callings:
                yield LLMResponse(
                    content=content,
                    thinking=thinking,
                    tool_callings=tool_callings
                )

        if pending_index is not None:
            tool_calling = ToolCalling(
                name=pending_name,
                arguments=json.loads(pending_args) if pending_args else {}
            )
            full_tool_callings.append(tool_calling)
            yield LLMResponse(tool_callings=[tool_calling])

        return LLMResponse(
            content="".join(full_content) if full_content else None,
            thinking="".join(full_thinking) if full_thinking else None,
            tool_callings=full_tool_callings if full_tool_callings else None
        )
    finally:
        if client is not None and hasattr(client, "close"):
            client.close()
