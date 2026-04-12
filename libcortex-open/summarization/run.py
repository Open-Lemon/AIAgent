#!/usr/bin/env python3

__author__ = "xi"

from libentry import ArgumentParser
from libentry.mcp.service import run_service

from summarization.service import SummarizationConfig, SummarizationService


def main():
    parser = ArgumentParser()
    parser.add_schema("config", SummarizationConfig)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--num_workers", type=int, default=1)
    parser.add_argument("--num_threads", type=int, default=100)
    args = parser.parse_args()

    run_service(
        SummarizationService,
        args.config,
        host=args.host,
        port=args.port,
        num_workers=args.num_workers,
        num_threads=args.num_threads,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
