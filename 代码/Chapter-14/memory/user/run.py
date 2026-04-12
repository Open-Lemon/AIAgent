#!/usr/bin/env python3

__author__ = "ai"

from libentry import ArgumentParser
from libentry.mcp.service import run_service

from memory.user.service import UserMemoryConfig, UserMemoryService


def main():
    parser = ArgumentParser()
    parser.add_schema("config", UserMemoryConfig)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    run_service(UserMemoryService, args.config, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
