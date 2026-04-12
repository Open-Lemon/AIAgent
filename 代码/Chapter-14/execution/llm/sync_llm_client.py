from typing import Iterable, Optional, Dict

from openai import OpenAI
from openai.types.chat import ChatCompletion
import httpx

from agent_types.common import LLMConfig, GenerationOptions


class LLMGenerationOptions(GenerationOptions):
    """LLM生成的相关选项"""
    stream: bool = False
    extra_body: Optional[Dict] = None
    temperature: float = 0


def sync_request_llm(
    llm_config: LLMConfig,
    user_prompt,
    system_prompt: str = "",
    tools: Iterable = None,
    generation_config: LLMGenerationOptions = LLMGenerationOptions()
) -> ChatCompletion:
    api_key = llm_config.api_key
    base_url = llm_config.base_url
    model_name = llm_config.model
    if system_prompt == "":
        messages = [
            {
                "role": "user",
                "content": f"""{user_prompt}"""
            }
        ]
    else:
        messages = [
            {
                "role": "system",
                "content": f"""{system_prompt}"""
            },
            {
                "role": "user",
                "content": f"""{user_prompt}"""
            }
        ]

    http_client = httpx.Client(verify=False)

    client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
    completion = client.chat.completions.create(
        model=model_name,
        messages=messages,
        stream=generation_config.stream,
        temperature=generation_config.temperature,
        tools=tools,
        extra_body=generation_config.extra_body,
        timeout=30,
        max_tokens=generation_config.max_tokens
    )
    return completion
