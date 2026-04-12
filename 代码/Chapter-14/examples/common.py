#!/usr/bin/env python3

__author__ = "xi"

from pydantic import BaseModel, Field

from agent_types.common import Request, Response


################################################################################
# 服务相关的数据结构定义
# 如果这些结构定义比较多，推荐单独写成一个文件
# 注意：绝大多数的Request和Response对象已经在agent_types中集中定义好了，请严格按照既有定义实现（Config对象除外）
################################################################################

class ExampleConfig(BaseModel):
    """该服务的配置
    在服务类的构造函数中传入配置对象
    配置对象可以在服务启动的时候构建，比如通过解析配置文件获取，或命令行参数获取
    """

    name: str = Field(
        title="服务名称",
        description="当前内容仅为例子，实际配置属性请基于模块具体需求定义"
    )
    root_dir: str = Field(
        title="根目录",
        description="当前内容仅为例子，实际配置属性请基于模块具体需求定义",
        default="./"
    )


class ExampleRequest(Request):
    """一个具体服务调用的请求
    本质上相当于把函数的众多入参打包在一个数据结构传入函数
    """

    # 这里设置request的名称，如果没有设置，那么默认的request名称就是这个类名去掉"Request"后缀之后的snake名称
    # __request_name__用于生成对应远程请求时的路径信息，即每个Request对象都会继承到一个get_request_path()的函数，这个path可以用到两个地方：
    # （1）定义服务的时候，@api.post()的path参数，之前post中不填path参数，现在可以直接把request类传进去；
    # （2）客户端请求服务的时候，client.post("/xxxx", request)，之前需要手动写path参数，现在可以直接传request，client.post(request)。
    # 这样改的好处是我们在实现服务的时候，不用再额外约定path了，都默认使用对应request对象中的__request_name__
    __request_name__ = "give_example"

    speed: int = Field(
        title="输出的速度",
        description="当前内容仅为例子，实际参数请基于模块具体需求定义",
        default=50
    )
    stream: bool = Field(
        title="是否采用流式输出",
        description="当前内容仅为例子，实际参数请基于模块具体需求定义",
        default=False
    )


class ExampleResponse(Response):
    """一个具体服务调用的响应
    尽可能定义JSON支持的数据类型，尽管传输层也支持np.ndarray以及bytes类型，但编解码会额外消耗CPU，应当尽量避免使用
    """

    content: str = Field(
        title="输出的内容",
        description="当前内容仅为例子，实际参数请基于模块具体需求定义",
        default=""
    )
