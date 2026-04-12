#!/usr/bin/env python3

__author__ = "xi"

from time import sleep
from typing import Iterable, Union

from libentry.mcp import api

from examples.common import ExampleConfig, ExampleRequest, ExampleResponse


################################################################################
# 一个服务对应一个class
# 其构造函数中定义一些配置信息、一些状态、资源等等，但是在成员函数中通过self使用对象属性的时候，应当注意线程安全问题
# 通常在对 self.xxx 进行读写操作的时候需要加锁（如threading.Lock）
################################################################################


class ExampleService:

    def __init__(self, config: ExampleConfig):
        self.config = config

    @api.route(ExampleRequest)
    def do_something(self, request: ExampleRequest) -> Union[ExampleResponse, Iterable[ExampleResponse]]:
        """以 @api.route() 装饰的函数就可以暴露给别的模块通过http或https协议调用
        这个函数为一个例子，其返回值同时支持“流式”和“非流式”输出，即使ExampleResponse和Iterable[ExampleResponse]类型
        通常情况下在没有明确流式输出需求的情况下，不用考虑流式输出，这里仅作为一种参考
        """
        if request.stream:
            return (
                ExampleResponse(content=content)
                for content in self._iter_content(__file__, request.speed)
            )
        else:
            full_content = "".join(self._iter_content(__file__, request.speed))
            return ExampleResponse(content=full_content)

    def _iter_content(self, path: str, speed: int) -> Iterable[str]:
        with open(path, "r") as f:
            while True:
                content = f.read(speed)
                sleep(0.01)
                if not content:
                    break
                yield content
