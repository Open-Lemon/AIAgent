#!/usr/bin/env python3

__author__ = "xi"

from typing import Dict, List, Union

import libdata
from libdata.url import URL
from libentry import logger
from libentry.mcp import api
from libentry.resource import ResourceManager
from pydantic import BaseModel, Field

from agent_types.common import ChatMessage, Mention, SessionMemory
from agent_types.memory.session import (
    ReadChatHistoryRequest,
    ReadChatHistoryResponse,
    ReadMentionsRequest,
    ReadMentionsResponse,
    ReadSessionMemoryRequest,
    ReadSessionMemoryResponse,
    ReadSessionPreferenceRequest,
    ReadSessionPreferenceResponse,
    WriteChatHistoryRequest,
    WriteChatHistoryResponse,
    WriteMentionsRequest,
    WriteMentionsResponse,
    WriteSessionPreferenceRequest,
    WriteSessionPreferenceResponse,
)


class SessionMemoryConfig(BaseModel):
    """Memory服务配置"""

    resource: str = Field(
        title="资源管理器",
        description="可以是本地yaml文件，或者远程管理服务地址"
    )
    mongodb: str = Field(
        title="MongoDB数据库",
        description="对应资源管理器中的MongoDB数据库的资源名称",
        default="mongodb"
    )


class SessionMemoryService:

    def __init__(self, config: SessionMemoryConfig):
        self.config = config

        self.resource_manager = ResourceManager(self.config.resource)
        mongo_url = self.resource_manager.get(self.config.mongodb)
        logger.info(f"Using {mongo_url} as database.")

        mongo_url = URL.ensure_url(mongo_url)
        self.chat_history_url = mongo_url.model_copy()
        self.chat_history_url.path = mongo_url.path.rstrip("/") + "/chat_history"
        logger.info(f"Using {self.chat_history_url.to_string()} as chat history collection.")
        with libdata.LazyMongoClient.from_url(self.chat_history_url) as mongo_client:
            # 创建session_id索引（用于查询优化）
            mongo_client.get_collection().create_index("session_id")
            # 创建session_id+turn_id复合唯一索引（确保组合唯一性）
            mongo_client.get_collection().create_index([("session_id", 1), ("turn_id", 1)], unique=True)

        self.mentions_url = mongo_url.model_copy()
        self.mentions_url.path = mongo_url.path.rstrip("/") + "/mentions"
        logger.info(f"Using {self.mentions_url.to_string()} as mentions collection.")
        with libdata.LazyMongoClient.from_url(self.mentions_url) as mongo_client:
            mongo_client.get_collection().create_index("session_id")
            # mentions可能在同一个turn_id下有多条记录，所以不设置唯一索引
            mongo_client.get_collection().create_index([("session_id", 1), ("turn_id", 1)])

        self.session_preference_url = mongo_url.model_copy()
        self.session_preference_url.path = mongo_url.path.rstrip("/") + "/session_preference"
        logger.info(f"Using {self.session_preference_url.to_string()} as session preference collection.")
        with libdata.LazyMongoClient.from_url(self.session_preference_url) as mongo_client:
            mongo_client.get_collection().create_index("session_id")
            # session_preference需要session_id+turn_id唯一
            mongo_client.get_collection().create_index([("session_id", 1), ("turn_id", 1)], unique=True)

    @api.post()
    def read_session_memory(self, request: ReadSessionMemoryRequest) -> ReadSessionMemoryResponse:
        chat_history = self._read_chat_history(request.session_id, request.n)
        mentions = self._read_mentions(request.session_id, request.n)
        session_preference = self._read_session_preference(request.session_id)
        if request.session_memory is None:
            memory = SessionMemory(
                chat_history=chat_history,
                mentions=mentions,
                session_preference=session_preference
            )
        else:
            memory = request.session_memory
            memory.chat_history = chat_history
            memory.mentions = mentions
            memory.session_preference = session_preference
        return ReadSessionMemoryResponse(session_memory=memory)

    @api.post()
    def read_chat_history(self, request: ReadChatHistoryRequest) -> ReadChatHistoryResponse:
        chat_history = self._read_chat_history(request.session_id, request.n)

        if request.session_memory is None:
            memory = SessionMemory(chat_history=chat_history)
        else:
            memory = request.session_memory
            memory.chat_history = chat_history

        return ReadChatHistoryResponse(
            chat_history=chat_history,
            session_memory=memory
        )

    @api.post()
    def read_mentions(self, request: ReadMentionsRequest) -> ReadMentionsResponse:
        mentions = self._read_mentions(request.session_id, request.n)

        if request.session_memory is None:
            memory = SessionMemory(mentions=mentions)
        else:
            memory = request.session_memory
            memory.mentions = mentions

        return ReadMentionsResponse(
            mentions=mentions,
            session_memory=memory
        )

    @api.post()
    def read_session_preference(self, request: ReadSessionPreferenceRequest) -> ReadSessionPreferenceResponse:
        preference = self._read_session_preference(request.session_id)

        if request.session_memory is None:
            memory = SessionMemory(session_preference=preference)
        else:
            memory = request.session_memory
            memory.session_preference = preference

        return ReadSessionPreferenceResponse(
            session_preference=preference,
            session_memory=memory
        )

    def _read_chat_history(self, session_id: Union[str, int], n: int) -> List[ChatMessage]:
        mongo_client = libdata.LazyMongoClient.from_url(self.chat_history_url)
        turn_ids = mongo_client.distinct("turn_id", {"session_id": session_id})

        if len(turn_ids) == 0:
            return []

        turn_ids.sort()
        min_turn_id = turn_ids[-n] if len(turn_ids) >= n else 1

        cur = mongo_client.find(
            {"session_id": session_id, "turn_id": {"$gte": min_turn_id}},
            projection={"_id": 0},
            sort=[("turn_id", 1)]
        )
        return [
            ChatMessage.model_validate(doc)
            for doc in cur
        ]

    def _read_mentions(self, session_id: Union[str, int], n: int) -> List[Mention]:
        mongo_client = libdata.LazyMongoClient.from_url(self.mentions_url)
        turn_ids = mongo_client.distinct("turn_id", {"session_id": session_id})

        if len(turn_ids) == 0:
            return []

        turn_ids.sort()
        min_turn_id = turn_ids[-n] if len(turn_ids) >= n else 1

        cur = mongo_client.find(
            {"session_id": session_id, "turn_id": {"$gte": min_turn_id}},
            projection={"_id": 0},
            sort=[("turn_id", 1)]
        )
        return [
            Mention.model_validate(doc)
            for doc in cur
        ]

    def _read_session_preference(self, session_id: Union[str, int]) -> Dict[str, str]:
        mongo_client = libdata.LazyMongoClient.from_url(self.session_preference_url)
        doc = mongo_client.find_one({"session_id": session_id}, sort=[("turn_id", -1)])
        return doc["preference"] if doc is not None else None

    @api.post()
    def write_chat_history(self, request: WriteChatHistoryRequest) -> WriteChatHistoryResponse:
        mongo_client = libdata.LazyMongoClient.from_url(self.chat_history_url)
        turn_id = request.turn_id
        with mongo_client.start_session():
            if turn_id is None:
                doc = mongo_client.find_one({"session_id": request.session_id}, sort=[("turn_id", -1)])
                turn_id = doc.get("turn_id", 1) + 1 if doc is not None else 1
            message = ChatMessage(
                content=request.content,
                metadata=request.metadata,
                role=request.role,
                turn_id=turn_id,
                thinking=request.thinking
            )
            doc = message.model_dump()
            doc["session_id"] = request.session_id
            mongo_client.update_one(
                query={"session_id": request.session_id, "turn_id": turn_id},
                update={"$set": doc},
                upsert=True
            )
        return WriteChatHistoryResponse(num_written=1)

    @api.post()
    def write_mentions(self, request: WriteMentionsRequest) -> WriteMentionsResponse:
        mongo_client = libdata.LazyMongoClient.from_url(self.mentions_url)
        turn_id = request.turn_id
        with mongo_client.start_session():
            if turn_id is None:
                doc = mongo_client.find_one({"session_id": request.session_id}, sort=[("turn_id", -1)])
                turn_id = doc.get("turn_id", 1) + 1 if doc is not None else 1

            mentions = request.mentions
            if not isinstance(mentions, List):
                mentions = [mentions]

            for m in mentions:
                if m.turn_id is None:
                    m.turn_id = turn_id
                doc = m.model_dump()
                doc["session_id"] = request.session_id
                mongo_client.insert_one(doc, flush=False)
            mongo_client.flush()
        return WriteMentionsResponse(num_written=len(mentions))

    @api.post()
    def write_session_preference(self, request: WriteSessionPreferenceRequest) -> WriteSessionPreferenceResponse:
        mongo_client = libdata.LazyMongoClient.from_url(self.session_preference_url)
        turn_id = request.turn_id
        with mongo_client.start_session():
            if turn_id is None:
                doc = mongo_client.find_one({"session_id": request.session_id}, sort=[("turn_id", -1)])
                turn_id = doc.get("turn_id", 1) + 1 if doc is not None else 1

            doc = {
                "session_id": request.session_id,
                "turn_id": turn_id,
                "preference": request.session_preference
            }
            mongo_client.update_one(
                query={"session_id": request.session_id, "turn_id": turn_id},
                update={"$set": doc},
                upsert=True
            )

        return WriteSessionPreferenceResponse(num_written=1)
