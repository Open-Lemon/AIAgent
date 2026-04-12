#!/usr/bin/env python3

__author__ = "xi"

from libentry import ArgumentParser
from libentry.mcp.service import RunServiceConfig, run_service

from planning.service import PlanningService, PlanningServiceConfig


def main():
    parser = ArgumentParser()
    parser.add_schema("run", RunServiceConfig)
    parser.add_schema("config", PlanningServiceConfig)
    args = parser.parse_args()

    run_service(PlanningService, args.config, args.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
