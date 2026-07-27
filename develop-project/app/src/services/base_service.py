import torch
from langchain_huggingface import HuggingFaceEmbeddings
from neo4j import GraphDatabase
from langchain_openai import ChatOpenAI
from graphdatascience import GraphDataScience

from app.src.core.config import settings
import os

# os.environ["LANGCHAIN_TRACING"] = settings.LANGSMITH_TRACING
# os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
# os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
# os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
class BaseService:
    def __init__(self):
        self.qdrant_url = settings.QDRANT_URL
        self.qdrant_colection = settings.QDRANT_COLECTION
        self.rerank_model_name = settings.MODEL_RERANKING
        self.llm_url = settings.LLM_URL
        self.model_llm = settings.MODEL_LLM
        self.llm_api_keys = settings.LLM_API_KEY.split(",")
        self.llm_temperature = settings.LLM_TEMPERATURE
        self.llm_top_p = settings.LLM_TOP_P
        self.limit_search_results = settings.LIMIT_SEARCH_RESULTS
        self.min_score = settings.MIN_SCORE
        self.top_k_rerank = settings.TOP_K_RERANK
        self.embedding_model_name = settings.MODEL_EMBEDDING
        self.neo4j_url = settings.NEO4J_URL
        self.neo4j_user = settings.NEO4J_USERNAME
        self.neo4j_password = settings.NEO4J_PASSWORD

        self.embedding_model_var = self.embedding_model()
        self.graphdb_var = self.graphdb()
        self.llm_model_var = self.llm_model()
        self.gds_var = self.gds()


    def embedding_model(self):
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"[Startup] Using device: {device}")

        return HuggingFaceEmbeddings(
            model_name=self.embedding_model_name,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": False},
        )

    def graphdb(self):
        return GraphDatabase.driver(
            self.neo4j_url,
            auth=(self.neo4j_user, self.neo4j_password)
        )
    def gds(self):
        return GraphDataScience(
            self.neo4j_url,
            auth=(self.neo4j_user, self.neo4j_password)
        )
    def llm_model(self):
        # return ChatGoogleGenerativeAI(
        #     model=self.model_llm,
        #     convert_system_message_to_human=True,
        #     temperature=self.llm_temperature,
        #     top_p=self.llm_top_p,
        #     api_key=self.llm_api_keys[0]  # Sử dụng khóa API đầu tiên từ danh sách
        # )
        return ChatOpenAI(
            model=self.model_llm,
            temperature=self.llm_temperature,
            top_p=self.llm_top_p,
            api_key=self.llm_api_keys[0],  # Sử dụng khóa API đầu tiên từ danh sách
            base_url=self.llm_url,
            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            },
            timeout=120,
            max_retries=0
        )
    

base_service = BaseService()