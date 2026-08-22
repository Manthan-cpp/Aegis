from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from services.auth import CurrentUser, get_current_user, verify_session_token
from services.direct_messages import (
    DirectMessageError,
    create_conversation,
    get_messages,
    list_conversations,
    search_profiles,
    send_message,
    sync_profile,
)
from services.dm_realtime import publish, subscribe, unsubscribe


router = APIRouter(prefix="/dm", tags=["direct-messages"])


class ProfileRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    display_name: str | None = Field(default=None, max_length=120)


class ConversationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)


class MessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2_000)
    client_message_id: str | None = Field(default=None, min_length=8, max_length=100)


def _run(action):
    try:
        return action()
    except DirectMessageError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error


@router.post("/profile")
def update_profile(payload: ProfileRequest, user: CurrentUser = Depends(get_current_user)):
    return _run(lambda: sync_profile(user.user_id, payload.username, payload.display_name))


@router.get("/users")
def find_users(
    query: str = Query(default="", max_length=64),
    user: CurrentUser = Depends(get_current_user),
) -> list[dict[str, str]]:
    return _run(lambda: search_profiles(user.user_id, query))


@router.get("/conversations")
def conversations(user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    return _run(lambda: list_conversations(user.user_id))


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def start_conversation(payload: ConversationRequest, user: CurrentUser = Depends(get_current_user)) -> dict[str, Any]:
    return _run(lambda: create_conversation(user.user_id, payload.username))


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, user: CurrentUser = Depends(get_current_user)) -> list[dict[str, Any]]:
    return _run(lambda: get_messages(user.user_id, conversation_id))


@router.post("/conversations/{conversation_id}/messages", status_code=status.HTTP_201_CREATED)
def add_message(
    conversation_id: str,
    payload: MessageRequest,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    message = _run(
        lambda: send_message(
            user.user_id,
            conversation_id,
            payload.content,
            payload.client_message_id,
        )
    )
    publish(conversation_id, {"type": "message", "message": message})
    return message


@router.websocket("/conversations/{conversation_id}/stream")
async def conversation_stream(websocket: WebSocket, conversation_id: str):
    """Push new messages to both currently open conversation panels."""

    await websocket.accept()
    subscription = None
    try:
        auth_payload = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        token = auth_payload.get("token") if isinstance(auth_payload, dict) else ""
        user = verify_session_token(str(token or ""))
        # Validate the signed-in user is one of the two participants before
        # subscribing to any real-time events.
        await asyncio.to_thread(get_messages, user.user_id, conversation_id, 1)
        subscription = subscribe(conversation_id, asyncio.get_running_loop())
        await websocket.send_json({"type": "ready"})
        while True:
            event = await subscription.queue.get()
            await websocket.send_json(event)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        return
    except HTTPException:
        await websocket.close(code=1008, reason="Sign in to use private messages.")
    except DirectMessageError:
        await websocket.close(code=1008, reason="You do not have access to this conversation.")
    finally:
        if subscription is not None:
            unsubscribe(conversation_id, subscription)
