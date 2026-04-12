#!/usr/bin/env python3

from typing import List, Optional

from agent_types.common import FewShot, SystemMemory
from agent_types.memory.system import (
    ReadDomainKnowledgeRequest,
    ReadDomainKnowledgeResponse,
    ReadFewShotsRequest,
    ReadFewShotsResponse,
    ReadReflectionsRequest,
    ReadReflectionsResponse,
    ReadSystemMemoryRequest,
    ReadSystemMemoryResponse,
    WriteDomainKnowledgeRequest,
    WriteDomainKnowledgeResponse,
    WriteFewShotsRequest,
    WriteFewShotsResponse,
    WriteReflectionsRequest,
    WriteReflectionsResponse,
)
from agent_types.retrieval import RetrievalRequest, RetrievalResponse
from libentry.mcp import api
from libentry.mcp.client import APIClient
from pydantic import BaseModel, Field


class SystemMemoryServiceConfig(BaseModel):
    mcp_retrieval_service_url: str = Field(description="MCP Retrieval Service URL")
    few_shots_collection: str = Field(description="Few Shots Collection")
    domain_knowledge_collection: str = Field(description="Domain Knowledge Collection")
    reflections_collection: str = Field(description="Reflections Collection")


class SystemMemoryService:

    def __init__(self, config: SystemMemoryServiceConfig):
        self.config = config
        self.client = APIClient(base_url=self.config.mcp_retrieval_service_url)
        self.few_shots_collection = self.config.few_shots_collection
        self.domain_knowledge_collection = self.config.domain_knowledge_collection
        self.reflections_collection = self.config.reflections_collection

    # def _get_num_written(self, results: Iterable[InsertResponse]) -> int:
    #     num_written = 0
    #     for r in results:
    #         if isinstance(r, InsertResponse):
    #             if r.insert_count > 0:
    #                 num_written = r.insert_count
    #     return num_written

    @api.post()
    def read_system_memory(
        self, request: ReadSystemMemoryRequest
    ) -> ReadSystemMemoryResponse:
        few_shots = self._read_few_shots(request.module_name, request.query, request.n, request.threshold)
        domain_knowledge = self._read_domain_knowledge(
            request.module_name, request.query, request.n, request.threshold
        )
        reflections = self._read_reflections(
            request.module_name, request.query, request.n, request.threshold
        )

        if request.system_memory is None:
            memory = SystemMemory(
                few_shots=few_shots,
                domain_knowledge=domain_knowledge,
                reflections=reflections,
            )
        else:
            memory = request.system_memory
            memory.few_shots = few_shots
            memory.domain_knowledge = domain_knowledge
            memory.reflections = reflections

        return ReadSystemMemoryResponse(system_memory=memory)

    @api.post()
    def write_few_shots(self, request: WriteFewShotsRequest) -> WriteFewShotsResponse:
        # documents = []
        # for fs in request.few_shots:
        #     doc = {
        #         "input": fs.input,
        #         "output": fs.output or "",
        #         "thinking": fs.thinking or "",
        #         "text": fs.input,
        #         "module_name": request.module_name,
        #     }
        #     documents.append(doc)

        # insert_req = InsertRequest(
        #     collection=self.few_shots_collection,
        #     documents=documents,
        #     indexed_field="text",
        #     indexed_related_field="text",
        # )
        # results = self.client.insert_data(insert_req)
        # return WriteFewShotsResponse(num_written=self._get_num_written(results))
        raise "请在平台导入few_shots"

    @api.post()
    def read_few_shots(self, request: ReadFewShotsRequest) -> ReadFewShotsResponse:
        few_shots = self._read_few_shots(request.module_name, request.query, request.n, request.threshold)

        if request.system_memory is None:
            memory = SystemMemory(few_shots=few_shots)
        else:
            memory = request.system_memory
            memory.few_shots = few_shots

        return ReadFewShotsResponse(few_shots=few_shots, system_memory=memory)

    def _read_few_shots(
            self,
            module_name: str,
            query: str,
            n: int,
            threshold: Optional[float]
    ) -> List[FewShot]:
        # Request all relevant metadata fields
        output_fields = ["input", "output", "thinking"]
        retrieval_req = RetrievalRequest(
            collections=[self.few_shots_collection],
            query=query,
            top_k=n,
            expr={self.few_shots_collection: f"module_name == '{module_name}'"},
            output_fields=output_fields,
        )
        retrieval_resp = RetrievalResponse.model_validate(self.client.post(retrieval_req))

        few_shots = []
        for fs, score in zip(retrieval_resp.items, retrieval_resp.scores):
            if score < threshold:
                continue
            few_shots.append(
                FewShot(
                    input=fs.get("input"),
                    output=fs.get("output"),
                    thinking=fs.get("thinking"),
                )
            )
        return few_shots

    @api.post()
    def write_domain_knowledge(
        self, request: WriteDomainKnowledgeRequest
    ) -> WriteDomainKnowledgeResponse:
        # documents = []
        # for dk in request.domain_knowledge:
        #     doc = {
        #         "knowledge": dk,
        #         "text": dk,  # Use the knowledge itself for embedding
        #         "module_name": request.module_name,
        #     }
        #     documents.append(doc)

        # insert_req = InsertRequest(
        #     collection=self.domain_knowledge_collection,
        #     documents=documents,
        #     indexed_field="text",
        #     indexed_related_field="text",
        # )
        # results = self.client.insert_data(insert_req)
        # return WriteDomainKnowledgeResponse(num_written=self._get_num_written(results))
        raise "请在平台导入domain_knowledge"

    @api.post()
    def read_domain_knowledge(
        self, request: ReadDomainKnowledgeRequest
    ) -> ReadDomainKnowledgeResponse:
        domain_knowledge = self._read_domain_knowledge(
            request.module_name, request.query, request.n, request.threshold
        )

        if request.system_memory is None:
            memory = SystemMemory(domain_knowledge=domain_knowledge)
        else:
            memory = request.system_memory
            memory.domain_knowledge = domain_knowledge

        return ReadDomainKnowledgeResponse(
            domain_knowledge=domain_knowledge, system_memory=memory
        )

    def _read_domain_knowledge(
            self,
            module_name: str,
            query: str,
            n: int,
            threshold: Optional[float]
    ) -> List[str]:
        output_fields = ["knowledge"]
        retrieval_req = RetrievalRequest(
            collections=[self.domain_knowledge_collection],
            query=query,
            top_k=n,
            expr={self.domain_knowledge_collection: f"module_name == '{module_name}'"},
            output_fields=output_fields,
            use_rerank=True
        )
        retrieval_resp = RetrievalResponse.model_validate(self.client.post(retrieval_req))

        domain_knowledge = []
        for item, score in zip(retrieval_resp.items, retrieval_resp.scores):
            print(f"{score}:\t{item.get('knowledge')}")  # todo: debug
            if score < threshold:
                continue
            if "knowledge" in item:
                domain_knowledge.append(item["knowledge"])

        return domain_knowledge

    @api.post()
    def write_reflections(
        self, request: WriteReflectionsRequest
    ) -> WriteReflectionsResponse:
        # documents = []
        # for r in request.reflections:
        #     doc = {
        #         "reflection": r,
        #         "text": r,  # Use the reflection itself for embedding
        #         "module_name": request.module_name,
        #     }
        #     documents.append(doc)

        # insert_req = InsertRequest(
        #     collection=self.reflections_collection,
        #     documents=documents,
        #     indexed_field="text",
        #     indexed_related_field="text",
        # )
        # results = self.client.insert_data(insert_req)
        # return WriteReflectionsResponse(num_written=self._get_num_written(results))
        raise "请在平台导入reflections"

    @api.post()
    def read_reflections(
        self, request: ReadReflectionsRequest
    ) -> ReadReflectionsResponse:
        reflections = self._read_reflections(
            request.module_name, request.query, request.n, request.threshold
        )

        if request.system_memory is None:
            memory = SystemMemory(reflections=reflections)
        else:
            memory = request.system_memory
            memory.reflections = reflections

        return ReadReflectionsResponse(reflections=reflections, system_memory=memory)

    def _read_reflections(
            self,
            module_name: str,
            query: str,
            n: int,
            threshold: Optional[float]
    ) -> List[str]:
        output_fields = ["reflection"]
        retrieval_req = RetrievalRequest(
            collections=[self.reflections_collection],
            query=query,
            top_k=n,
            expr={self.reflections_collection: f"module_name == '{module_name}'"},
            output_fields=output_fields,
            use_rerank=True
        )
        retrieval_resp = RetrievalResponse.model_validate(self.client.post(retrieval_req))

        reflections = []
        for item, score in zip(retrieval_resp.items, retrieval_resp.scores):
            if score < threshold:
                continue
            if "reflection" in item:
                reflections.append(item["reflection"])

        return reflections


# if __name__ == "__main__":
#     import logging
#     from pathlib import Path
#
#     import yaml
#
#     logger = logging.getLogger()
#     logger.setLevel("INFO")
#     config_path = Path(__file__).parent / "system_memory_config.yaml"
#     with open(config_path, "r") as f:
#         config_data = yaml.safe_load(f)
#     config = SystemMemoryServiceConfig(**config_data)
#     service = SystemMemoryService(config)
#     res = service.read_few_shots(
#         ReadFewShotsRequest(
#             collection="system_memory_fewshots",
#             module_name="这是一条测试数据",
#             query="这试数据",
#             n=10,
#         )
#     )
#     print(res)
