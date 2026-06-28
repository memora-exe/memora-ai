import asyncio
import os
from google.genai import types
from google.adk import Agent
from google.adk.runners import InMemoryRunner
from google.adk.sessions import Session, InMemorySessionService
from app.core.config import settings

# Đảm bảo API key được set cho Gemini model
if settings.GOOGLE_API_KEY:
    os.environ["GOOGLE_API_KEY"] = settings.GOOGLE_API_KEY

# Define a simple tool (can be replaced with LangChain tools later)
def get_project_info(project_id: str) -> dict:
    """Returns information about a project.

    Args:
        project_id (str): The ID of the project to look up.

    Returns:
        dict: Project information including id, name, and status.
    """
    return {"id": project_id, "name": "Memora Project", "status": "Active"}

# Initialize the ADK Agent
memora_agent = Agent(
    name="memora_assistant",
    model="gemini-2.5-flash",
    instruction="You are a helpful assistant for the Memora project. Answer user questions accurately and use tools if needed.",
    tools=[get_project_info]
)

# Khởi tạo InMemoryRunner để chạy Agent
app_name = "memora"
session_service = InMemorySessionService()
runner = InMemoryRunner(
    agent=memora_agent,
    app_name=app_name,
)
# Enable auto-create session (not exposed in InMemoryRunner constructor)
runner.auto_create_session = True


async def _get_or_create_session(session_id: str) -> Session:
    """Lấy session có sẵn hoặc tạo mới nếu chưa tồn tại."""
    existing = await session_service.get_session(app_name=app_name, user_id="default", session_id=session_id)
    if existing:
        return existing
    return await session_service.create_session(
        app_name=app_name,
        user_id="default",
        session_id=session_id,
    )


async def process_chat_message(message: str, session_id: str) -> str:
    """
    Process a chat message using the ADK Agent (full response).
    """
    # Đảm bảo session tồn tại
    await _get_or_create_session(session_id)

    # Create content object
    content = types.Content(parts=[types.Part(text=message)], role='user')

    final_response = ""
    async for event in runner.run_async(
        user_id="default",
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_response = event.content.parts[0].text or ""

    return final_response if final_response else "Sorry, I could not process your request."


async def process_chat_message_stream(message: str, session_id: str):
    """
    Process a chat message and yield chunks for SSE (Server-Sent Events).
    """
    # Đảm bảo session tồn tại
    await _get_or_create_session(session_id)

    # Create content object
    content = types.Content(parts=[types.Part(text=message)], role='user')

    async for event in runner.run_async(
        user_id="default",
        session_id=session_id,
        new_message=content,
    ):
        if event.content and event.is_final_response():
            yield event.content
        elif event.content:
            # Partial (non-final) content chunks
            yield event.content
