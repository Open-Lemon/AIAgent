#!/usr/bin/env python3

__author__ = "ai"

from datetime import datetime
from typing import Any, Dict

import libdata
from libdata.url import URL
from libentry import logger
from libentry.mcp import api
from libentry.resource import ResourceManager
from pydantic import BaseModel, Field

from agent_types.common import UserMemory
from agent_types.memory.user import (
    ReadUserMemoryRequest,
    ReadUserMemoryResponse,
    ReadUserPreferenceRequest,
    ReadUserPreferenceResponse,
    ReadUserProfileRequest,
    ReadUserProfileResponse,
    WriteUserPreferenceRequest,
    WriteUserPreferenceResponse,
    WriteUserProfileRequest,
    WriteUserProfileResponse,
)


class UserMemoryConfig(BaseModel):
    """用户记忆服务配置"""

    resource: str = Field(
        title="资源管理器", description="可以是本地yaml文件，或者远程管理服务地址"
    )
    mongodb: str = Field(
        title="MongoDB数据库",
        description="对应资源管理器中的MongoDB数据库的资源名称",
        default="mongodb",
    )


class UserMemoryService:

    def __init__(self, config: UserMemoryConfig):
        self.config = config

        self.resource_manager = ResourceManager(self.config.resource)
        mongo_url = self.resource_manager.get(self.config.mongodb)
        logger.info(f"Using {mongo_url} as database.")
        mongo_url = URL.ensure_url(mongo_url)

        # User Profile Collection
        self.user_profile_url = mongo_url.model_copy()
        self.user_profile_url.path = mongo_url.path.rstrip("/") + "/user_profile"
        logger.info(f"Using {self.user_profile_url.to_string()} as user profile collection.")
        with libdata.LazyMongoClient.from_url(self.user_profile_url) as mongo_client:
            mongo_client.get_collection().create_index([("user_id", 1)], unique=True)

        # User Preference Collection
        self.user_preference_url = mongo_url.model_copy()
        self.user_preference_url.path = mongo_url.path.rstrip("/") + "/user_preference"
        logger.info(f"Using {self.user_preference_url.to_string()} as user preference collection.")
        with libdata.LazyMongoClient.from_url(self.user_preference_url) as mongo_client:
            mongo_client.get_collection().create_index([("user_id", 1)], unique=True)

    @api.post()
    def read_user_memory(self, request: ReadUserMemoryRequest) -> ReadUserMemoryResponse:
        profile = self._read_user_profile(request.user_id)
        preference = self._read_user_preference(request.user_id)

        if request.user_memory is None:
            memory = UserMemory(user_profile=profile, user_preference=preference)
        else:
            memory = request.user_memory
            memory.user_profile = profile
            memory.user_preference = preference
        return ReadUserMemoryResponse(user_memory=memory)

    @api.post()
    def read_user_profile(self, request: ReadUserProfileRequest) -> ReadUserProfileResponse:
        profile = self._read_user_profile(request.user_id)
        if request.user_memory is None:
            memory = None
        else:
            memory = request.user_memory
            memory.user_profile = profile
        return ReadUserProfileResponse(user_profile=profile, user_memory=memory)

    @api.post()
    def write_user_profile(self, request: WriteUserProfileRequest) -> WriteUserProfileResponse:
        mongo_client = libdata.LazyMongoClient.from_url(self.user_profile_url)

        result = mongo_client.update_one(
            {"user_id": request.user_id},
            {
                "$set": {
                    "profile": request.user_profile,
                    "last_updated": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        return WriteUserProfileResponse(
            num_written=result.modified_count or result.upserted_id is not None
        )

    @api.post()
    def read_user_preference(self, request: ReadUserPreferenceRequest) -> ReadUserPreferenceResponse:
        preference = self._read_user_preference(request.user_id)
        if request.user_memory is None:
            memory = None
        else:
            memory = request.user_memory
            memory.user_preference = preference
        return ReadUserPreferenceResponse(
            user_preference=preference, user_memory=memory
        )

    @api.post()
    def write_user_preference(self, request: WriteUserPreferenceRequest) -> WriteUserPreferenceResponse:
        mongo_client = libdata.LazyMongoClient.from_url(self.user_preference_url)

        result = mongo_client.update_one(
            {"user_id": request.user_id},
            {
                "$set": {
                    "preference": request.user_preference,
                    "last_updated": datetime.utcnow(),
                }
            },
            upsert=True,
        )
        return WriteUserPreferenceResponse(
            num_written=result.modified_count or result.upserted_id is not None
        )

    def _read_user_profile(self, user_id: str) -> Dict[str, Any]:
        mongo_client = libdata.LazyMongoClient.from_url(self.user_profile_url)
        doc = mongo_client.find_one({"user_id": user_id}, projection={"_id": 0})
        return doc.get("profile", {}) if doc else {}

    def _read_user_preference(self, user_id: str) -> Dict[str, Any]:
        mongo_client = libdata.LazyMongoClient.from_url(self.user_preference_url)
        doc = mongo_client.find_one({"user_id": user_id}, projection={"_id": 0})
        return doc.get("preference", {}) if doc else {}
