"""Three ADK agents (retriever, analyst, responder) chained as one SequentialAgent.

State flows through the ADK session: each agent writes its answer to `output_key`,
and later agents read it back with {key} placeholders in their instruction.

NOTE: ADK moves fast. If an import or argument below is rejected, check the current
ADK docs for McpToolset and StdioConnectionParams.
"""
import os
import sys

from google.adk.agents import LlmAgent, SequentialAgent
from mcp import StdioServerParameters

import config

try:  # newer ADK spells it McpToolset, older versions use MCPToolset
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
except ImportError:
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset as McpToolset

try:  # newer ADK wraps the stdio params, older versions take StdioServerParameters directly
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
except ImportError:
    StdioConnectionParams = None


def make_toolset(tool_names: list[str]) -> McpToolset:
    """Start our MCP server as a subprocess and expose only the named tools to one agent.

    Least privilege: the retriever gets search only, the analyst gets SQL only.
    """
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(config.PROJECT_ROOT),
        env=dict(os.environ),  # stdio servers get a minimal env by default, so pass ours through
    )
    connection_params = (
        StdioConnectionParams(server_params=server_params, timeout=60)
        if StdioConnectionParams
        else server_params
    )
    return McpToolset(connection_params=connection_params, tool_filter=tool_names)


# --- Agent 1: retriever ---
RETRIEVER_INSTRUCTION = """
You find complaints that are relevant to the user's question.
1. Call vector_search_complaints once with the user's question as the query and top_k=8.
2. Output a compact list. One line per complaint: complaint_id | product | issue | one-sentence gist.
3. If the tool returns an error, output the error text and nothing else.
Do not answer the question yourself.
"""

retriever_agent = LlmAgent(
    name="retriever",
    model=config.GEMINI_MODEL,
    description="Finds semantically similar complaints with BigQuery vector search.",
    instruction=RETRIEVER_INSTRUCTION,
    tools=[make_toolset(["vector_search_complaints"])],
    output_key="retrieved",
)

# --- Agent 2: analyst ---
ANALYST_INSTRUCTION = """
You answer the quantitative part of the question with BigQuery SQL.
Complaints found by the retriever, for context:
{retrieved}

Steps:
1. Decide whether the question needs numbers (counts, trends, top companies, rates). If not,
   output exactly: No quantitative analysis needed.
2. Call describe_schema once, then write ONE standard SQL SELECT using fully qualified table names.
   Use COUNT and GROUP BY where it helps, and always include a LIMIT.
3. Call run_sql. If it returns an error, fix the query and retry, at most 2 retries.
4. Output the SQL you ran and a short plain summary of the rows. Never invent numbers.
"""

analyst_agent = LlmAgent(
    name="analyst",
    model=config.GEMINI_MODEL,
    description="Runs read-only SQL on BigQuery for counts and trends.",
    instruction=ANALYST_INSTRUCTION,
    tools=[make_toolset(["describe_schema", "run_sql"])],
    output_key="analysis",
)

# --- Agent 3: responder ---
RESPONDER_INSTRUCTION = """
You write the final answer for a customer support analyst.
Use ONLY the evidence below. Do not use outside knowledge.

Similar complaints:
{retrieved}

SQL analysis:
{analysis}

Rules:
- Answer the user's question directly in under 150 words.
- Cite complaint IDs for claims taken from complaints, and mention the SQL result for any numbers.
- If the evidence is thin or an error appears above, say so plainly instead of guessing.
- The data is masked. Never try to guess or reconstruct names or contact details.
"""

responder_agent = LlmAgent(
    name="responder",
    model=config.GEMINI_MODEL,
    description="Writes the final grounded answer.",
    instruction=RESPONDER_INSTRUCTION,
)

# --- The workflow: retriever -> analyst -> responder ---
root_agent = SequentialAgent(
    name="support_workflow",
    description="Retrieve similar complaints, analyze with SQL, then answer.",
    sub_agents=[retriever_agent, analyst_agent, responder_agent],
)
