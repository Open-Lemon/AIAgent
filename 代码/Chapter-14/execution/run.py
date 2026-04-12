#!/usr/bin/env python3


import yaml
from libentry import ArgumentParser
from libentry.mcp.service import run_service

from execution.service import ToolExecutor, ToolExecutorConfig


def main():
    parser = ArgumentParser()
    parser.add_argument("--config-path", type=str)
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=15000)

    args = parser.parse_args()
    with open(args.config_path) as f:
        config_dict = yaml.safe_load(f)
    config = ToolExecutorConfig.model_validate(config_dict)
    run_service(
        ToolExecutor,
        config,
        host=args.host,
        port=args.port
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
