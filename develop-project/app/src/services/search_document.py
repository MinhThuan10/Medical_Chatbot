
# ---Create Index---

# // Document
# CREATE CONSTRAINT document_file_name_unique IF NOT EXISTS
# FOR (d:Document)
# REQUIRE d.file_name IS UNIQUE;


# // Chunk
# CREATE CONSTRAINT chunk_chunk_id_unique IF NOT EXISTS
# FOR (c:Chunk)
# REQUIRE c.chunk_id IS UNIQUE;


# // EntityMention
# CREATE CONSTRAINT entity_mention_id_unique IF NOT EXISTS
# FOR (e:EntityMention)
# REQUIRE e.mention_id IS UNIQUE;


# // Community
# CREATE CONSTRAINT community_id_unique IF NOT EXISTS
# FOR (c:Community)
# REQUIRE c.community_id IS UNIQUE;


# CREATE VECTOR INDEX `entity-embeddings`
# FOR (e:EntityMention) ON (e.embedding)
# OPTIONS {indexConfig: {
#  `vector.dimensions`: 768,
#  `vector.similarity_function`: 'cosine'
# }};

# CREATE FULLTEXT INDEX `entity-fulltext`
# FOR (e:EntityMention)
# ON EACH [e.name, e.description]


# CREATE VECTOR INDEX community_embedding_index
# FOR (c:Community)
# ON (c.embedding)
# OPTIONS {
#     indexConfig: {
#         `vector.dimensions`: 768,
#         `vector.similarity_function`: 'cosine'
#     }
# }




# MATCH (e:EntityMention)
# WHERE NOT (e)-[:RELATED_TO]-()
# RETURN count(e) AS isolated_entities;

# import os
# import sys

# # develop-project/
# PROJECT_ROOT = os.path.abspath(
#     os.path.join(os.path.dirname(__file__), "../../..")
# )

# if PROJECT_ROOT not in sys.path:
#     sys.path.insert(0, PROJECT_ROOT)

from torch import chunk

from app.src.services.base_service import base_service
from pydantic import BaseModel, Field  

class DriftEvidence(BaseModel):
    chunks: list

class LocalSearch():
    def hybrid_search(
        self,
        query,
        top_k=15,
        source_k=20,
        rrf_constant=60
    ):

        query_embedding = base_service.embedding_model_var.embed_query(query)
        cypher = """
        CALL {

            // -------- Fulltext Search --------
            CALL db.index.fulltext.queryNodes(
                'entity-fulltext',
                $query,
                {limit:$source_k}
            )
            YIELD node, score

            WITH collect(node) AS nodes

            UNWIND range(0, size(nodes)-1) AS rank

            RETURN
                nodes[rank] AS entity,
                1.0 / ($rrf_constant + rank + 1) AS contribution

            UNION ALL

            // -------- Vector Search --------
            CALL db.index.vector.queryNodes(
                'entity-embeddings',
                $source_k,
                $query_embedding
            )
            YIELD node, score

            WITH collect(node) AS nodes

            UNWIND range(0, size(nodes)-1) AS rank

            RETURN
                nodes[rank] AS entity,
                1.0 / ($rrf_constant + rank + 1) AS contribution


        }

        WITH
            entity,
            sum(contribution) AS hybrid_score

        RETURN
            elementId(entity) AS entity_id,
            entity.name AS name,
            entity.description AS description,
            hybrid_score

        ORDER BY hybrid_score DESC
        LIMIT $top_k
        """

        records, _, _ = base_service.graphdb_var.execute_query(
            cypher,
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            source_k=source_k,
            rrf_constant=rrf_constant,
        )

        return [dict(r) for r in records]
    
    def expand_graph(
        self,
        seed_entities,
    ):
        """
        Expand graph từ seed entities.

        Return:
            - related_entities
            - relationships
        """

        entity_ids = [e["entity_id"] for e in seed_entities]

        cypher = """
        MATCH (e:EntityMention)-[r]-(n:EntityMention)
        WHERE elementId(e) IN $entity_ids

        RETURN
            elementId(e) AS source_id,
            e.name AS source_name,

            elementId(r) AS relationship_id,
            type(r) AS relationship_type,
            r.description AS relationship_description,
            r.weight AS weight,

            elementId(n) AS target_id,
            n.name AS target_name,
            n.description AS target_description
        """

        records, _, _ = base_service.graphdb_var.execute_query(
            cypher,
            entity_ids=entity_ids,
        )

        relationships = []
        related_entities = {}

        for record in records:

            relationships.append({
                "source_id": record["source_id"],
                "target_id": record["target_id"],
                "type": record["relationship_type"],
                "description": record["relationship_description"],
                "weight": record["weight"]

            })

            if record["target_id"] not in related_entities:

                related_entities[record["target_id"]] = {
                    "entity_id": record["target_id"],
                    "name": record["target_name"],
                    "description": record["target_description"],
                }

        return (list(related_entities.values()), relationships)
        
    def ranking_filter_entity_relationship(self,
    seed_entities,
    related_entities,
    relationships,
    top_k=10):
        """
        Ranking related entities và filter graph.

        Entity score = Σ(seed_score * relationship.weight)
        """

        # ------------------------------------
        # Seed score
        # ------------------------------------
        seed_scores = {
            entity["entity_id"]: entity["hybrid_score"]
            for entity in seed_entities
        }

        # ------------------------------------
        # Entity score
        # ------------------------------------
        entity_scores = {}

        for rel in relationships:

            source_id = rel["source_id"]
            target_id = rel["target_id"]

            # Chỉ propagate từ seed
            if source_id not in seed_scores:
                continue

            score = seed_scores[source_id] * rel["weight"] / 10

            entity_scores[target_id] = (
                entity_scores.get(target_id, 0)
                + score
            )

        # ------------------------------------
        # Gán score cho related entity
        # ------------------------------------
        ranked_entities = []

        for entity in related_entities:

            entity = entity.copy()

            entity["score"] = entity_scores.get(
                entity["entity_id"],
                0.0
            )
            ranked_entities.append(entity)

        # ------------------------------------
        # Sort
        # ------------------------------------
        ranked_entities.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        # ------------------------------------
        # Filter
        # ------------------------------------
        filtered_entities = ranked_entities[:top_k]

        entity_ids = {
            entity["entity_id"]
            for entity in filtered_entities
        }

        seed_ids = {
            entity["entity_id"]
            for entity in seed_entities
        }

        # ------------------------------------
        # Filter relationship
        # ------------------------------------
        filtered_relationships = []

        for rel in relationships:

            if (
                rel["source_id"] in seed_ids
                and
                rel["target_id"] in entity_ids
            ):

                filtered_relationships.append(rel)

        return (
            filtered_entities,
            filtered_relationships,
        )
    
    def retrieve_chunks(
        self,
        seed_entities,
        filtered_entities,
    ):
        """
        Retrieve candidate chunks từ seed entities và filtered entities.

        Return:
            [
                {
                    "chunk_id": ...,
                    "text": ...,
                    "title": ...,
                    "url": ...,
                    "entity_ids": [...]
                }
            ]
        """

        # ------------------------------------------
        # Candidate entities
        # ------------------------------------------

        entity_ids = list({
            e["entity_id"]
            for e in (seed_entities + filtered_entities)
        })

        # ------------------------------------------
        # Query
        # ------------------------------------------

        cypher = """
        MATCH (c:Chunk)-[:MENTIONS]->(e:EntityMention)
        WHERE elementId(e) IN $entity_ids

        RETURN
            elementId(c) AS chunk_id,
            c.chunk_text AS chunk_text,
            c.title AS chunk_title,
            c.url AS chunk_url,
            collect(DISTINCT elementId(e)) AS entity_ids
        """

        records, _, _ = base_service.graphdb_var.execute_query(
            cypher,
            entity_ids=entity_ids,
        )

        chunks = []

        for record in records:

            chunks.append({
                "chunk_id": record["chunk_id"],
                "text": record["chunk_text"],
                "title": record["chunk_title"],
                "url": record["chunk_url"],
                "entity_ids": record["entity_ids"],
            })

        return chunks
    
    # def retrieve_document_info(self, chunks):
    #     """
    #     Query document information for the given chunks.
    #     """
    #     if not chunks:
    #         return {}

    #     chunk_ids = [chunk["chunk_id"] for chunk in chunks]

    #     cypher = """
    #     MATCH (d:Document)-[:HAS_CHUNK]->(c:Chunk)
    #     WHERE elementId(c) IN $chunk_ids
    #     RETURN
    #         elementId(c) AS chunk_id,
    #         elementId(d) AS doc_id,
    #         d.title AS doc_title,
    #         d.url AS doc_url
    #     """

    #     records, _, _ = base_service.graphdb_var.execute_query(
    #         cypher,
    #         chunk_ids=chunk_ids,
    #     )

    #     doc_info = {}
    #     for record in records:
    #         doc_info[record["chunk_id"]] = {
    #             "doc_id": record["doc_id"],
    #             "doc_title": record["doc_title"],
    #             "doc_url": record["doc_url"]
    #         }
    #         print(f"Retrieved document info for chunk_id {record['chunk_id']}: {doc_info[record['chunk_id']]}")
    #     return doc_info

    def retrieve_communities(
        self,
        seed_entities,
        filtered_entities,
    ):
        """
        Retrieve candidate communities từ seed entities và filtered entities.

        Return:
            [
                {
                    "community_id": ...,
                    "title": ...,
                    "summary": ...,
                    "level": ...,
                    "entity_ids": [...]
                }
            ]
        """

        # ------------------------------------------
        # Candidate entities
        # ------------------------------------------

        entity_ids = list({
            e["entity_id"]
            for e in (seed_entities + filtered_entities)
        })

        # ------------------------------------------
        # Query
        # ------------------------------------------

        cypher = """
        MATCH (e:EntityMention)-[:IN_COMMUNITY]->(c:Community)
        WHERE elementId(e) IN $entity_ids

        RETURN
            elementId(c) AS community_id,
            c.title AS title,
            c.summary AS summary,
            c.level AS level,
            collect(DISTINCT elementId(e)) AS entity_ids
        """

        records, _, _ = base_service.graphdb_var.execute_query(
            cypher,
            entity_ids=entity_ids,
        )

        communities = []

        for record in records:

            communities.append({
                "community_id": record["community_id"],
                "title": record["title"],
                "summary": record["summary"],
                "level": record["level"],
                "entity_ids": record["entity_ids"],
            })

        return communities

    def ranking_filter_chunks_and_community(
        self,
        seed_entities,
        related_entities,
        chunks,
        communities,
        chunk_top_k=10,
        community_top_k=5,
    ):
        """
        Ranking & filter chunks và communities.

        Chunk:
            - Ưu tiên chunk chứa nhiều candidate entities nhất.

        Community:
            - Ưu tiên community chứa nhiều candidate entities nhất.
            - Nếu bằng nhau thì ưu tiên level cao hơn.
        """

        # ----------------------------------------------------
        # Candidate entity ids
        # ----------------------------------------------------
        seed_entity_ids = {
            e["entity_id"]
            for e in seed_entities
        }
        
        candidate_entity_ids = {
            e["entity_id"]
            for e in (seed_entities + related_entities)
        }

        # ----------------------------------------------------
        # Rank Chunks
        # ----------------------------------------------------

        ranked_chunks = []

        for chunk in chunks:
            matched_seed = set(chunk["entity_ids"]) & seed_entity_ids

            matched_related = (
                set(chunk["entity_ids"]) & candidate_entity_ids
            ) - seed_entity_ids

            if len(matched_seed) < 2:
                continue

            chunk = chunk.copy()
            chunk["seed_match_count"] = len(matched_seed)
            chunk["related_match_count"] = len(matched_related)

            ranked_chunks.append(chunk)

        ranked_chunks.sort(
            key=lambda x: (
                x["seed_match_count"],
                x["related_match_count"],
            ),
            reverse=True,
        )      
        

        ranked_chunks = ranked_chunks[:chunk_top_k]
        print(f"Ranked chunks: {[ (x['seed_match_count'], x['related_match_count']) for x in ranked_chunks ]}")
        # ----------------------------------------------------
        # Rank Communities
        # ----------------------------------------------------

        ranked_communities = []

        for community in communities:
            matched_seed = set(community["entity_ids"]) & seed_entity_ids

            matched_related = (
                set(community["entity_ids"]) & candidate_entity_ids
            ) - seed_entity_ids

            if len(matched_seed) < 2:
                continue



            community = community.copy()
            community["seed_match_count"] = len(matched_seed)
            community["related_match_count"] = len(matched_related)

            ranked_communities.append(community)

        ranked_communities.sort(
            key=lambda x: (
                x["seed_match_count"],
                x["related_match_count"],
                x["level"],
            ),
            reverse=True,
        )

        ranked_communities = ranked_communities[:community_top_k]

        return ranked_chunks, ranked_communities
    
    def build_context(
        self,
        seed_entities,
        related_entities,
        relationships,
        chunks,
        communities,
    ):
        """
        Build structured context cho LLM.
        """

        context = {
            "entities": [],
            "relationships": [],
            "chunks": [],
            "communities": [],
        }

        # ------------------------------------------------
        # Seed entities
        # ------------------------------------------------

        for entity in seed_entities:

            context["entities"].append({
                "type": "seed",
                "name": entity["name"],
                "description": entity["description"]
                
            })

        # ------------------------------------------------
        # Related entities
        # ------------------------------------------------

        for entity in related_entities:

            context["entities"].append({
                "type": "related",
                "name": entity["name"],
                "description": entity["description"]
            })

        # ------------------------------------------------
        # Relationships
        # ------------------------------------------------

        for relationship in relationships:

            context["relationships"].append({
                "source": relationship["source_id"],
                "target": relationship["target_id"],
                "type": relationship["type"],
                "description": relationship["description"],
                "weight": relationship["weight"],
            })

        # ------------------------------------------------
        # Chunks
        # ------------------------------------------------

        for chunk in chunks:
            context["chunks"].append({
                "text": chunk["text"],
                "title": chunk.get("title"),
                "url": chunk.get("url"),
            })


        # ------------------------------------------------
        # Communities
        # ------------------------------------------------

        for community in communities:

            context["communities"].append({
                "title": community["title"],
                "summary": community["summary"],
                "level": community["level"],
            })
        

        return context

    def format_context_for_llm(self, context):
        sections = []
        chunk_map = {}

        # # ---------------- Entity ----------------
        # sections.append("# Entities")
        # for entity in context["entities"]:
        #     sections.append(
        #         f"- {entity['name']}: {entity['description']}"
        #     )

        # # ---------------- Relationship ----------------
        # sections.append("\n# Relationships")
        # for relation in context["relationships"]:
        #     sections.append(
        #         f"- {relation['description']}"
        #     )

        # # ---------------- Community ----------------
        # sections.append("\n# Communities")
        # for community in context["communities"]:
        #     sections.append(
        #         f"- {community['summary']}"
        #     )

        # ---------------- Chunk ----------------
        sections.append("\n# Chunks")

        for chunk_id, chunk in enumerate(context["chunks"]):
            sections.append(
                                f"""
                    =====================
                    Chunk ID: {chunk_id}

                    {chunk['text']}
                    """.strip()
                            )

            chunk_map[str(chunk_id)] = {
                "chunk_id": chunk_id,
                "title": chunk.get("title", ""),
                "url": chunk.get("url", ""),
                "text": chunk["text"]
            }

        llm_context = "\n".join(sections)

        return llm_context, chunk_map

    def local_search(self, query):
        seed_entities = self.hybrid_search(query)

        related_entities, relationships = self.expand_graph(seed_entities)

        filtered_entities, filtered_relationships = self.ranking_filter_entity_relationship(seed_entities, related_entities, relationships)

        chunks = self.retrieve_chunks(seed_entities, filtered_entities)

        communities = self.retrieve_communities(seed_entities, filtered_entities)

        ranked_chunks, ranked_communities = self.ranking_filter_chunks_and_community(seed_entities, filtered_entities, chunks, communities)

        # doc_info = self.retrieve_document_info(ranked_chunks)
        
        # for chunk in ranked_chunks:
        #     info = doc_info.get(chunk["chunk_id"], {})
        #     chunk["doc_title"] = info.get("doc_title")
        #     chunk["doc_url"] = info.get("doc_url")

        context = self.build_context(seed_entities, filtered_entities, filtered_relationships, ranked_chunks, ranked_communities)

        format_context, chunk_map = self.format_context_for_llm(context)
        return {
            "context": format_context,
            "chunk_map": chunk_map,
            "raw_context": context
        }

    def drift_local_search(self, query):
        seed_entities = self.hybrid_search(query)

        related_entities, relationships = self.expand_graph(seed_entities)

        filtered_entities, _ = self.ranking_filter_entity_relationship(seed_entities, related_entities, relationships)

        chunks = self.retrieve_chunks(seed_entities, filtered_entities)


        ranked_chunks, _ = self.ranking_filter_chunks_and_community(seed_entities, filtered_entities, chunks, communities=[], chunk_top_k=5, community_top_k=3)

        return DriftEvidence(
                    chunks=ranked_chunks,
                )
    
    
local_search = LocalSearch()


class Finding(BaseModel):
    summary: str = Field(
        description="Relevant finding extracted from the community reports."
    )
    importance: int = Field(
        description="Importance score from 0 to 100.",
        ge=0,
        le=100,
    )
    community_id: str = Field(
        description="Community ID where this finding comes from."
    )
class MapSearchResponse(BaseModel):
    findings: list[Finding]


class GlobalSearch():

    def retrieve_communities(
        self,
        query,
        top_k=20,
    ):
        query_embedding = base_service.embedding_model_var.embed_query(query)

        cypher = """
        CALL db.index.vector.queryNodes(
            'community_embedding_index',
            $top_k,
            $embedding
        )
        YIELD node, score

        RETURN
            node.id AS id,
            node.level AS level,
            node.rank AS rank,
            node.title AS title,
            node.summary AS summary,
            node.key_entities AS key_entities,
            node.key_relationships AS key_relationships,
            node.findings AS findings,
            score

        ORDER BY score DESC
        """

        records, _, _ = base_service.graphdb_var.execute_query(
            cypher,
            embedding=query_embedding,
            top_k=top_k,
        )

        return [dict(record) for record in records]
    
    def split_communities(
        self,
        communities,
        batch_size=4,
    ):

        batches = []

        for i in range(0, len(communities), batch_size):

            batches.append(
                communities[i:i+batch_size]
            )

        return batches
    

    def build_community_context(
        self,
        community: dict,
    ) -> str:

        findings = community.get("findings") or []
        # key_entities = community.get("key_entities") or []
        # key_relationships = community.get("key_relationships") or []

        finding_text = ""

        if isinstance(findings, list):
            for i, finding in enumerate(findings, start=1):

                if isinstance(finding, dict):
                    text = finding.get("summary", "")
                else:
                    text = str(finding)

                finding_text += f"{i}. {text}\n"

        return f"""
    Title:
    {community.get("title","")}

    Summary:
    {community.get("summary","")}

    Findings:
    {finding_text}
    """.strip()

    def map_search(
        self,
        query: str,
        communities: list[dict],
    ) -> list[Finding]:
        """
        Extract relevant findings from a batch of Community Reports.
        """

        community_context = "\n\n-----------------------------\n\n".join(
            self.build_community_context(c)
            for c in communities
        )

        system_prompt = """
            You are an expert knowledge analyst.

            Your task is to analyze Community Reports and extract ONLY the findings that are relevant to the user's question.

            Rules:

            - Do NOT answer the user's question.
            - Do NOT summarize across different communities.
            - Do NOT infer information that is not explicitly stated.
            - Each finding must come from exactly ONE community.
            - Ignore irrelevant findings.
            - Assign an importance score between 0 and 100.
            - Return ONLY valid JSON.
            """

        user_prompt = f"""
            User Question   

            {query}

            Community Reports

            {community_context}
            """

        try:
            structured_llm = base_service.llm_model_var.with_structured_output(MapSearchResponse)
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_prompt
                }
            ])
            findings = response.findings if getattr(response, "findings", None) else []
        except Exception as exc:
            print(f"[LLM_ERROR] map_search failed: {exc}")
            findings = []

        return findings


    def build_findings_context(
        self,
        findings: list[Finding],
    ) -> str:

        contexts = []
        contexts.append("\n# Community")
        for idx, finding in enumerate(findings, start=1):

            contexts.append(f"""
                    Content:
                    {finding.summary}
                    """.strip())

        return "\n\n-----------------------------\n\n".join(contexts)

    def global_search(
        self,
        query: str,
        top_k: int = 15,
    ):

        # 1. Retrieve relevant communities
        communities = self.retrieve_communities(query)

        if not communities:
            return "Không tìm thấy Community liên quan."

        # 2. Split thành nhiều batch
        batches = self.split_communities(communities)

        # 3. Map Search: gọi nhiều batch cùng lúc thay vì tuần tự
        all_findings = []

        if not batches:
            return "Không tìm thấy thông tin phù hợp."

        try:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=min(2, len(batches))) as executor:
                batch_results = list(
                    executor.map(
                        lambda batch: self.map_search(query=query, communities=batch),
                        batches,
                    )
                )

            for findings in batch_results:
                if findings:
                    all_findings.extend(findings)

        except Exception:
            # Fallback: nếu thread pool không khả dụng thì vẫn chạy tuần tự
            for batch in batches:
                findings = self.map_search(
                    query=query,
                    communities=batch,
                )
                if findings:
                    all_findings.extend(findings)

        # Không tìm được finding
        if not all_findings:
            return "Không tìm thấy thông tin phù hợp."

        # 4. Ranking
        all_findings.sort(
            key=lambda x: x.importance,
            reverse=True,
        )

        seen = set()
        unique_findings = []

        for finding in all_findings:
            # Skip findings with low importance
            print(f"Finding: {finding.summary}, Importance: {finding.importance}")
            if finding.importance <= 60:
                continue

            if finding.summary not in seen:
                seen.add(finding.summary)
                unique_findings.append(finding)

        top_findings = unique_findings[:top_k]

        context = self.build_findings_context(top_findings)

        return {
            "context": context,
            "raw_context": top_findings
        }


global_search = GlobalSearch()


HYDE_PROMPT = """
    Bạn là chuyên gia phân tích tri thức.

    Người dùng sẽ đưa ra một câu hỏi.

    Hãy viết một đoạn tóm tắt như thể nó là một Community Report trong GraphRAG.

    Yêu cầu:

    - Khoảng 100-200 từ.
    - Bao gồm các entity chính.
    - Bao gồm các khái niệm liên quan.
    - Bao gồm các mối quan hệ giữa các entity.
    - Không trả lời trực tiếp câu hỏi.
    - Viết theo phong cách mô tả kiến thức tổng quan.
    - Không được bịa thông tin ngoài phạm vi hợp lý của câu hỏi.

    Question:
"""

class PrimerReasoningResult(BaseModel):
    intermediate_answer: str = Field(
        description="Initial answer generated only from the community reports."
    )

    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence score between 0 and 1."
    )

    follow_up_queries: list[str] = Field(
        description="A list of follow-up questions for Local Search."
    )


PRIMER_REASONING_PROMPT = """
You are an expert knowledge navigator for a GraphRAG system.

You are given:

1. The user's question.
2. Several high-level Community Reports retrieved from the knowledge graph.

Your tasks are:

1. Produce a concise intermediate answer using ONLY the provided community reports.
2. Estimate your confidence (0.0 - 1.0).
3. Determine which information is still missing.
4. Generate up to 3 follow-up questions that would retrieve the most useful missing information through Local Search.

Guidelines:

- Do NOT answer beyond the provided reports.
- The follow-up questions should be specific.
- Avoid duplicate questions.
- If the reports already provide sufficient information, return an empty list.
- Answer in User Question Language.

"""


class ReasoningResult(BaseModel):
    intermediate_answer: str = Field(
        description="Updated intermediate answer based on all retrieved evidence."
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0 and 1."
    )

    stop: bool = Field(
        description="Whether enough evidence has been collected."
    )

    follow_up_queries: list[str] = Field(
        description="Additional follow-up queries if more evidence is needed."
    )

REASON_OVER_EVIDENCE_PROMPT = """
You are performing the reasoning step of a DRIFT Search pipeline.

You are given:

1. The original user question.
2. The current intermediate answer.
3. Evidence collected from multiple Local Searches.

Your tasks are:

1. Update the intermediate answer using ONLY the provided evidence.
2. Estimate your confidence (0.0 - 1.0).
3. Decide whether the evidence is sufficient.
4. If more information is needed, generate up to 3 follow-up queries.
5. If the evidence is sufficient, set stop=true and return an empty follow_up_queries list.
"""  
# Hàm build_context đang bị cắt bớt thông tin tại vì context lenght của model LLM có giới hạn
class DriftSearch():

    
    def hyde_generation(self, query: str) -> str:
        """
        Generate a hypothetical community report (HyDE) from the user query.

        Parameters
        ----------
        query : str
            Original user query.

        Returns
        -------
        str
            Hypothetical community description for embedding.
        """


        try:
            response = base_service.llm_model_var.invoke([
                {
                    "role": "system",
                    "content": HYDE_PROMPT
                },
                {
                    "role": "user",
                    "content": ( f"Question:\n{query}\n\n")
                }
            ])
            return getattr(response, "content", "") or ""
        except Exception as exc:
            print(f"[LLM_ERROR] hyde_generation failed: {exc}")
            return ""

    def primer_search(self, hyde_generation: str, top_k: int = 5):
        communities = global_search.retrieve_communities(hyde_generation, top_k=top_k)
        return communities

    def primer_reasoning(self, query: str, communities: list,):
        """
        Generate an initial answer and follow-up questions
        from retrieved Community Reports.
        """

        community_context = "\n\n-----------------------------\n\n".join(
            global_search.build_community_context(c)
            for c in communities
        )
        try:
            structured_llm = base_service.llm_model_var.with_structured_output(PrimerReasoningResult)
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": PRIMER_REASONING_PROMPT
                },
                {
                    "role": "user",
                    "content": (f"User Question:\n{query}\n\n"
                                f"Community Reports:\n{community_context}\n\n")
                }
            ])
            return response
        except Exception as exc:
            print(f"[LLM_ERROR] primer_reasoning failed: {exc}")
            return PrimerReasoningResult(
                intermediate_answer="",
                confidence=0.0,
                follow_up_queries=[],
            )

    def drift_retrieval(
        self,
        follow_up_queries: list[str],
    ):

        results = []

        for q in follow_up_queries:

            result = local_search.drift_local_search(q)

            results.append(result)

        return results
    
    def merge_drift_evidence(
        self,
        evidences: list[DriftEvidence],
    ) -> DriftEvidence:
        """
        Merge evidence from multiple follow-up queries.
        """
        chunks = {}

        for evidence in evidences:

            for chunk in evidence.chunks or []:
                chunk_id = chunk.get("chunk_id")
                if chunk_id is None:
                    chunk_id = chunk.get("id")
                if chunk_id is not None:
                    chunks[chunk_id] = chunk

        return DriftEvidence(
            chunks=list(chunks.values()),
        )

    # def attach_document_info(self, evidence: DriftEvidence) -> DriftEvidence:
    #     """
    #     Enrich drift chunks with their source document metadata.
    #     """
    #     chunks = [chunk.copy() for chunk in (evidence.chunks or [])]
    #     # doc_info = local_search.retrieve_document_info(chunks)

    #     for chunk in chunks:
    #         info = doc_info.get(chunk.get("chunk_id"), {})
    #         chunk["doc_title"] = info.get("doc_title")
    #         chunk["doc_url"] = info.get("doc_url")

        return DriftEvidence(chunks=chunks)

    def format_context_for_llm(self, evidence: DriftEvidence):
        """
        Format DRIFT evidence like local search so citations can reuse chunk_map.
        """
        sections = ["\n# Chunks"]
        chunk_map = {}

        for chunk_id, chunk in enumerate(evidence.chunks or []):
            sections.append(
                f"""
                    =====================
                    Chunk ID: {chunk_id}

                    {chunk.get('text', '')}
                    """.strip()
            )

            chunk_map[str(chunk_id)] = {
                "chunk_id": chunk_id,
                "title": chunk.get("title", ""),
                "url": chunk.get("url", ""),
                "text": chunk.get("text", "")
            }

        return "\n".join(sections), chunk_map
   
    def build_context(self, evidence: DriftEvidence) -> dict[str, str]:
        """
        Build a compact evidence summary that is short enough for the
        reasoning prompt while preserving the most useful information.
        """


        def build_section(items, section_name: str) -> str:
            if not items:
                return f"{section_name}: Không có dữ liệu."

            compact_items = []
            # limited_items = items[:max_items]

            for idx, item in enumerate(items, start=1):
                if isinstance(item, dict):
                    # if section_name == "Entities":
                    #     name = item.get("name") or item.get("entity_id") or ""
                    #     description = compact_text(item.get("description") or "")
                    #     entry = f"{idx}. {name}"
                    #     if description:
                    #         entry += f": {description}"
                    #     compact_items.append(entry)
                    # elif section_name == "Relationships":
                    #     description = compact_text(
                    #         item.get("description")
                    #         or item.get("type")
                    #         or ""
                    #     )
                    #     compact_items.append(f"{idx}. {description}")
                    # elif section_name == "Communities":
                    #     title = compact_text(item.get("title") or "")
                    #     summary = compact_text(item.get("summary") or "")
                    #     entry = title or summary or str(item)
                    #     if summary and title and summary != title:
                    #         entry = f"{title}: {summary}"
                    #     compact_items.append(f"{idx}. {entry}")
                
                    if section_name == "Chunks":
                        text = item.get("text")
                        compact_items.append(f"{idx}. {text}")
                    
            return f"{section_name}:\n" + "\n".join(compact_items)

        return {
            "chunks": build_section(evidence.chunks or [], "Chunks"),
        }
    
    def reason_over_evidence(
        self,
        query: str,
        intermediate_answer: str,
        evidence: DriftEvidence,
    ) -> ReasoningResult:
        """
        Perform reasoning over merged evidence and decide
        whether another DRIFT iteration is required.

        The prompt is intentionally compacted to avoid sending the entire
        raw evidence payload to the LLM.
        """

        compact_context = self.build_context(evidence)

        try:
            structured_llm = base_service.llm_model_var.with_structured_output(ReasoningResult)
            response = structured_llm.invoke([
                {
                    "role": "system",
                    "content": REASON_OVER_EVIDENCE_PROMPT
                },
                {
                    "role": "user",
                    "content": (f"User Question:\n{query}\n\n"
                                f"Current Intermediate Answer:\n{intermediate_answer}\n\n"
                                f"Evidence:\n{compact_context['chunks']}\n\n")
                }
            ])
            return response
        except Exception as exc:
            print(f"[LLM_ERROR] reason_over_evidence failed: {exc}")
            return ReasoningResult(
                intermediate_answer=intermediate_answer,
                confidence=0.0,
                stop=True,
                follow_up_queries=[],
            )

    

    def drift_loop(
        self,
        query: str,
        intermediate_answer: str,
        follow_up_queries: list[str],
        max_depth: int = 3,
    ) -> tuple[str, DriftEvidence]:
        """
        Iteratively retrieve local evidence for follow-up queries until the
        reasoning step stops or the maximum depth is reached.
        """

        current_answer = intermediate_answer or ""
        current_queries = list(follow_up_queries or [])
        merged_evidence = DriftEvidence(
            chunks=[]
        )

        for _ in range(max_depth):
            if not current_queries:
                break

            evidences = self.drift_retrieval(current_queries)
            if not evidences:
                break

            current_evidence = self.merge_drift_evidence(evidences)
            if not any(
                [
                    current_evidence.chunks,
                ]
            ):
                break

            merged_evidence = self.merge_drift_evidence([merged_evidence, current_evidence])

            reasoning_result = self.reason_over_evidence(
                query=query,
                intermediate_answer=current_answer,
                evidence=merged_evidence,
            )

            current_answer = reasoning_result.intermediate_answer
            current_queries = list(reasoning_result.follow_up_queries or [])

            if reasoning_result.stop:
                break

        return current_answer, merged_evidence
    
    def drift_search(self, query):
        hyde_generation = self.hyde_generation(query)
        communities = self.primer_search(hyde_generation)
        primer_reasoning = self.primer_reasoning(query, communities)
        _, merged_evidence = self.drift_loop(
            query=query,
            intermediate_answer=primer_reasoning.intermediate_answer,
            follow_up_queries=primer_reasoning.follow_up_queries,
        )
        # merged_evidence = self.attach_document_info(merged_evidence)
        context, chunk_map = self.format_context_for_llm(merged_evidence)
        return {
            "context": context,
            "chunk_map": chunk_map,
            "raw_context": merged_evidence
        }

    
drift_search = DriftSearch()
