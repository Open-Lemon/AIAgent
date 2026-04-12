#!/usr/bin/env python3

__author__ = "xi"

from libentry import ArgumentParser
from libentry.mcp.service import run_service

from examples.common import ExampleConfig
from examples.service import ExampleService


def main():
    # 如果使用libentry中的ArgumentParser，则可以将配置的class作为参数，这样可以通过命令行设置其属性
    # 例如下面这种写法，在运行run.py的时候，就可以通过 --config.name "XX Name" 的形式设置ExampleConfig的name属性值
    parser = ArgumentParser()
    parser.add_schema("config", ExampleConfig)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--num_workers", type=int, default=1)
    parser.add_argument("--num_threads", type=int, default=50)
    args = parser.parse_args()

    run_service(
        service_type=ExampleService,
        service_config=args.config,
        host=args.host,
        port=args.port,
        num_workers=args.num_workers,
        num_threads=args.num_threads
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
