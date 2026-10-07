"""Runs the multi-agent workflow for one question and returns the answer plus the evidence."""
import time
import uuid

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.agents import root_agent

APP_NAME = "vertex_agent_platform"
USER_ID = "api-user"

session_service = InMemorySessionService()
runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)


async def run_pipeline(question: str) -> dict:
    """Run retriever -> analyst -> responder in a fresh session.

    Returns:
      answer      final text from the responder
      retrieved   what the retriever produced (used as grounding context in evaluation)
      analysis    what the analyst produced
      latency_ms  wall clock time for the whole workflow
    """
    session_id = uuid.uuid4().hex
    await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)

    user_message = types.Content(role="user", parts=[types.Part(text=question)])
    started_at = time.perf_counter()

    answer = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=user_message):
        # Every agent emits a final response. The last one belongs to the responder, so it wins.
        if event.is_final_response() and event.content and event.content.parts:
            answer = "".join(part.text or "" for part in event.content.parts)

    latency_ms = round((time.perf_counter() - started_at) * 1000)

    session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
    state = session.state if session else {}
    await session_service.delete_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)

    return {
        "answer": answer.strip(),
        "retrieved": state.get("retrieved", ""),
        "analysis": state.get("analysis", ""),
        "latency_ms": latency_ms,
    }
