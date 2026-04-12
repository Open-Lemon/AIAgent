#!/usr/bin/env python3

__author__ = "huangyuyb1"


from typing import List, Dict

import rich

from libentry.mcp.client import APIClient


def build_mcp_client(
    config: dict,
) -> Dict[str, APIClient]:
    """构建MCP客户端字典

    Args:
        config (dict): MCP服务器配置字典
    Returns:
        dict: 服务器名称到APIClient实例的映射
    """
    clients = {}
    mcp_servers = config
    for server_name, server_config in mcp_servers.items():
        url = server_config.get("url")
        if not server_config.get("enabled"):
            continue
        if not url:
            rich.print(f"[yellow]Warning: Missing URL for server {server_name}[/yellow]")
            continue

        try:
            client = APIClient(base_url=url)
            clients[server_name] = client
        except Exception as e:
            rich.print(f"[red]Error creating client for {server_name}: {str(e)}[/red]")
            continue

    return clients
