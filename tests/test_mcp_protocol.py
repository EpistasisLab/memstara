"""Exercise the real stdio MCP handshake and tool calls without an LLM."""

import json
import os
import sys
from datetime import timedelta

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

pytestmark = pytest.mark.protocol


async def test_data_server_protocol_and_target_isolation(tmp_path):
    dataset = tmp_path / "dataset.csv"
    dataset.write_text("signal,outcome\n1,0\n2,1\n3,0\n4,1\n")
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "memstara.mcp_servers.data"],
        env={**os.environ, "MEMSTARA_DATASET_PATH": str(dataset), "MEMSTARA_OUTPUT_DIR": str(tmp_path)},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=20)) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert {"describe_dataset", "slice_columns"} <= names
            result = await session.call_tool(
                "slice_columns", {"columns": ["signal"], "y_column": "outcome", "tag": "protocol"}
            )
            assert not result.isError
            payload = json.loads(result.content[0].text)
            assert "error" not in payload, payload
            from pathlib import Path

            assert Path(payload["path"]).read_text().splitlines()[0] == "signal,outcome"
            rejected = await session.call_tool(
                "slice_columns", {"columns": ["outcome"], "y_column": "outcome", "tag": "bad"}
            )
            assert rejected.isError or "error" in json.loads(rejected.content[0].text)
