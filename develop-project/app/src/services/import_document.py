import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from langchain_text_splitters import RecursiveCharacterTextSplitter
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid
from app.src.services.base_service import base_service


GRAPH_EXTRACTION_PROMPT = """
Extract entities and relationships from the Vietnamese medical text below.

ENTITY:
- entity_name: Exact name or phrase mentioned in the text.
- entity_type: Must be one of ["disease", "symptom", "drug", "treatment", "procedure", "test", "body_part", "department", "doctor", "organization", "risk_factor", "condition", "other"].
- entity_description: Brief description based only on the text.

RELATIONSHIP:
- source_entity: Must be an extracted entity.
- target_entity: Must be an extracted entity.
- relationship_description: Explain the relationship using only information from the text.
- relationship_strength: Score from 1.0 to 10.0 based on how explicitly the relationship is stated.

RULES:
1. Extract only entities explicitly mentioned or clearly described in the text.
2. Do not use external knowledge or infer unsupported information.
3. Do not merge synonyms, abbreviations, or aliases; entity resolution is handled separately.
4. Create a relationship only when the text explicitly states or clearly supports it.
5. Do not create relationships merely because two entities appear in the same sentence.
6. source_entity and target_entity must exactly match entity_name from the extracted entities.
7. Do not create self-relationships or duplicate relationships.

Text:
"""


class ImportedChunk(BaseModel):
    chunk_id: str
    file_name: str
    url: str
    title: str
    heading: str = ""
    chunk_text: str


class Entity(BaseModel):
    entity_name: str
    entity_type: str
    entity_description: str


class Relationship(BaseModel):
    source_entity: str
    target_entity: str
    relationship_description: str
    relationship_strength: float = 1.0


class ExtractionResult(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)


class CommunityReport(BaseModel):
    title: str = Field(
        description="Short title describing the main topic of the community."
    )

    summary: str = Field(
        description="Concise factual summary of the community."
    )

    key_entities: list[str] = Field(
        description="Important entities in the community."
    )

    key_relationships: list[str] = Field(
        description="Important relationships between entities."
    )

    findings: list[str] = Field(
        description="Important factual findings derived from the community."
    )


class ImportDocument:
    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 256,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.graphdb = base_service.graphdb_var
        self.llm = base_service.llm_model_var
        self.embedding_model = base_service.embedding_model_var
        self.gds = base_service.gds_var
        self.structured_llm_extraction_result = self.llm.with_structured_output(ExtractionResult)
        self.structured_llm_community_report = self.llm.with_structured_output(CommunityReport)
        self.max_workers = base_service.max_workers_var


    def import_db(
        self,
        file_path: str | os.PathLike,
        original_filename: str | None = None,
    ) -> dict[str, int]:
        """
        Import Document, Chunk, EntityMention and RELATED_TO relationships only.
        Community detection/report update is intentionally not run here.
        """


        documents, sections  = self.load_documents(file_path, original_filename=original_filename)

        chunks = self.chunk_documents(sections)
        stats = {
            "documents": 0,
            "chunks": 0,
            "entities": 0,
            "relationships": 0,
            "failed_chunks": 0,
        }

        if (self.check_document(documents)):
            return stats

    
        for document in documents:
            self.create_document(document)
            stats["documents"] += 1
        
        batch_size = 5000
        for i in range(0, len(chunks), batch_size):
            chunk_batch = chunks[i : i + batch_size]
            self.create_chunks_batch(chunk_batch)
            stats["chunks"] += len(chunk_batch)

        results = []

        print("Call LLM")
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:

            futures = {
                executor.submit(self.extract_graph, idx, row): idx
                for idx, row in enumerate(chunks)
            }
            total = len(chunks)

            for completed, future in enumerate(as_completed(futures), start=1):

                result = future.result()

                if result:

                    results.append(result)

                print(f"Đã xử lý {completed}/{total}")

        print(
            f"[Entity Update] "
            f"Saving {len(results)} extracted chunks..."
        )
        for i in range(0, len(results), batch_size):
            results_batch = results[i : i + batch_size]
            entities_count, relationships_count = self.create_entities_and_relationships_batch(results_batch)
            stats["entities"] += entities_count
            stats["relationships"] += relationships_count
        
        self.build_entity_mention_wcc()

        return stats

    def get_document_stats(self) -> dict[str, Any]:
        query = """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        OPTIONAL MATCH (c)-[:MENTIONS]->(e:EntityMention)

        WITH
            count(DISTINCT d) AS documents,
            count(DISTINCT c) AS chunks,
            count(DISTINCT e) AS entities

        OPTIONAL MATCH ()-[r:RELATED_TO]->()

        WITH
            documents,
            chunks,
            entities,
            count(DISTINCT r) AS relationships

        OPTIONAL MATCH (community:Community)

        RETURN
            documents,
            chunks,
            entities,
            relationships,
            count(DISTINCT community) AS communities
        """

        records, _, _ = self.graphdb.execute_query(query)
        totals = dict(records[0]) if records else {}

        file_type_query = """
        MATCH (d:Document)
        RETURN d.source_type AS source_type
        """

        type_records, _, _ = self.graphdb.execute_query(
            file_type_query
        )

        file_types = {
            "csv": 0,
            "pdf": 0,
            "other": 0,
        }

        for record in type_records:
            file_type = self.detect_file_type(
                record.get("source_type")
            )

            file_types[file_type] = (
                file_types.get(file_type, 0) + 1
            )

        return {
            "documents": totals.get("documents", 0),
            "chunks": totals.get("chunks", 0),
            "entities": totals.get("entities", 0),
            "relationships": totals.get("relationships", 0),
            "communities": totals.get("communities", 0),
            "file_types": file_types,
        }

    def list_documents(self, limit: int = 100) -> list[dict[str, Any]]:
        query = """
        MATCH (d:Document)
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        RETURN d.file_name AS file_name,
                d.source_type AS source_type,
               count(DISTINCT c) AS chunks
        ORDER BY file_name ASC
        LIMIT $limit
        """
        records, _, _ = self.graphdb.execute_query(query, limit=limit)
        documents = []
        for record in records:
            documents.append(
                {
                    "file_name": record.get("file_name", ""),
                    "source_type": record.get("source_type", ""),
                    "chunks": record.get("chunks", 0),
                }
            )
        return documents

    def delete_document(self, file_name: str) -> dict[str, int]:
        query = """
        MATCH (d:Document {file_name: $file_name})
        OPTIONAL MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
        OPTIONAL MATCH (c)-[:MENTIONS]->(e:EntityMention)
        WITH d, collect(DISTINCT c) AS chunks, collect(DISTINCT e) AS entities
        OPTIONAL MATCH (e1:EntityMention)-[r:RELATED_TO]-(e2:EntityMention)
        WHERE e1 IN entities OR e2 IN entities
        WITH d, chunks, entities, collect(DISTINCT r) AS relationships
        FOREACH (rel IN relationships | DELETE rel)
        FOREACH (entity IN entities | DETACH DELETE entity)
        FOREACH (chunk IN chunks | DETACH DELETE chunk)
        DETACH DELETE d
        RETURN size(chunks) AS chunks,
               size(entities) AS entities,
               size(relationships) AS relationships
        """
        records, _, _ = self.graphdb.execute_query(query, file_name=file_name)
        deleted = dict(records[0]) if records else {}
        return {
            "documents": 1 if records else 0,
            "chunks": deleted.get("chunks", 0),
            "entities": deleted.get("entities", 0),
            "relationships": deleted.get("relationships", 0),
        }

    def check_document(self, documents):
        query = """
        MATCH (d:Document {
            file_name: $file_name,
            source_type: $source_type
        })
        RETURN count(d) AS count
        """
        for document in documents:
            result = self.graphdb.execute_query(
                query,
                file_name=document["file_name"],
                source_type=document["source_type"],
            )
            if (result.records[0]["count"] > 0):
                return True
        return False

    def load_documents(
        self,
        file_path: str | os.PathLike,
        original_filename: str | None = None,
    ):
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return self.load_csv(path, original_filename=original_filename)
        if suffix == ".pdf":
            return self.load_pdf(path, original_filename=original_filename)

        raise ValueError("Only .csv and .pdf files are supported.")

    def load_csv(
        self,
        path: Path,
        original_filename: str | None = None,
    ) -> tuple[list[dict], list[dict]]:
        file_name = original_filename or path.name

        sections = []
        document_parts = []

        with path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:

            reader = csv.DictReader(file)

            for idx, row in enumerate(reader):

                text = self.first_value(
                    row,
                    ["content", "text", "chunk_text", "body"],
                )

                if not text:
                    continue

                url = (
                    self.first_value(
                        row,
                        ["url", "source", "file_path"],
                    )
                    or f"{path}#{idx}"
                )

                title = (
                    self.first_value(
                        row,
                        ["title", "heading", "name"],
                    )
                    or path.stem
                )

                heading = (
                    self.first_value(
                        row,
                        ["heading", "title"],
                    )
                    or title
                )

                # =========================
                # Section-level data
                # =========================
                sections.append(
                    {   
                        "file_name": file_name,
                        "url": url,
                        "title": title,
                        "heading": heading,
                        "text": text,
                        "row_id": idx + 2,
                    }
                )

                # =========================
                # Document-level data
                # =========================
                document_parts.append(
                    f"URL: {url}\n"
                    f"Title: {title}\n"
                    f"Heading: {heading}\n"
                    f"Content: {text}"
                )

        # =========================
        # File-level document
        # =========================
        documents = [
            {
                "file_name": file_name,
                "source_type": "csv",
                "text": "\n\n".join(document_parts),
            }
        ]

        return documents, sections

    def load_pdf(
        self,
        path: Path,
        original_filename: str | None = None,
    ) -> tuple[list[dict], list[dict]]:
        file_name = original_filename or path.name

        text = self.extract_pdf_text(path)
        if not text.strip():
            raise ValueError(f"PDF has no extractable text: {path}")

        url = str(path)
        title = Path(file_name).stem
        heading = Path(file_name).stem

        # =========================
        # Document-level data
        # =========================
        documents = [
            {
                "file_name": file_name,
                "source_type": "csv",
                "text": text,
            }
        ]

        # =========================
        # Section-level data
        # =========================
        sections = [
            {
                "file_name": file_name,
                "url": "",
                "title": title,
                "heading": "",
                "text": text,
            }
        ]
        return documents, sections

    def extract_pdf_text(self, path: Path) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            pass

        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError as exc:
            raise ImportError("Install pypdf or pdfplumber to import PDF files.") from exc

    def chunk_documents(self, documents) -> list[ImportedChunk]:
        chunks = []
        for document in documents:
            for idx, chunk_text in enumerate(self.split_text(document["text"])):
                chunks.append(
                    ImportedChunk(
                        chunk_id = str(uuid.uuid4()),
                        file_name=document["file_name"],
                        url=document["url"],
                        title=document["title"],
                        heading=document["heading"],
                        chunk_text=chunk_text,
                    )
                )

        return chunks

    def split_text(self, text: str) -> list[str]:
        text = self.normalize_text(text)
        if not text:
            return []

        chunks = []
        # start = 0
        # text_len = len(text)
        # while start < text_len:
        #     end = min(start + self.chunk_size, text_len)
        #     chunk = text[start:end].strip()
        #     if chunk:
        #         chunks.append(chunk)
        #     if end == text_len:
        #         break
        #     start = max(end - self.chunk_overlap, start + 1)
        
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024,
            chunk_overlap=256,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        doc_chunks = splitter.split_text(text)
        for chunk in doc_chunks:
            chunks.append(chunk)
            
        return chunks

    def extract_graph(self, idx, row):
        try:
            if isinstance(row, dict):
                chunk_id = row["chunk_id"]
                url = row["url"]
                title = row["title"]
                heading = row["heading"]
                text = str(row["chunk_text"]).strip()

            else:
                chunk_id = row.chunk_id
                url = row.url
                title = row.title
                heading = row.heading
                text = str(row.chunk_text).strip()

            if not text:
                return None
            
            response = self.structured_llm_extraction_result.invoke([
                {
                    "role": "system",
                    "content": GRAPH_EXTRACTION_PROMPT
                },
                {
                    "role": "user",
                    "content": (f"Input text:\n{text}\n\n")
                }
            ])
            # response là một object của ExtractionResult
            extracted_text = response
            return {
                "chunk_id": chunk_id,
                "url": url,
                "title": title,
                "heading": heading,
                "chunk_text": text,
                "extracted_text": extracted_text.model_dump(), 
            }

        except Exception as e:
            print(f"Lỗi chunk {idx}: {e}")
            return None

    def create_document(self, document) -> None:
        query = """
        MERGE (d:Document {file_name: $file_name})
        SET d.file_name = $file_name,
            d.source_type = $source_type,
            d.text = $text

        """
        self.graphdb.execute_query(
            query,
            file_name=document["file_name"],
            source_type=document["source_type"],
            text=document["text"],
            
        )

    def create_chunk(self, chunk: ImportedChunk) -> None:
        query = """
        MATCH (d:Document {file_name: $file_name})
        MERGE (c:Chunk {chunk_id: $chunk_id})
        SET c.chunk_id = $chunk_id,
            c.url = $url,
            c.title = $title,
            c.chunk_text = $chunk_text,
            c.heading = $heading
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
        self.graphdb.execute_query(
            query,
            file_name = chunk.file_name,
            chunk_id = chunk.chunk_id,
            url=chunk.url,
            title = chunk.title,
            chunk_text=chunk.chunk_text,
            heading=chunk.heading,
        )

    def create_chunks_batch(self, chunks: list[ImportedChunk]) -> None:
        if not chunks:
            return
        rows = []
        for chunk in chunks:
            rows.append({
                "file_name": chunk.file_name,
                "chunk_id": chunk.chunk_id,
                "url": chunk.url,
                "title": chunk.title,
                "chunk_text": chunk.chunk_text,
                "heading": chunk.heading,
            })
        query = """
        UNWIND $rows AS row
        MATCH (d:Document {file_name: row.file_name})
        MERGE (c:Chunk {chunk_id: row.chunk_id})
        SET c.chunk_id = row.chunk_id,
            c.url = row.url,
            c.title = row.title,
            c.chunk_text = row.chunk_text,
            c.heading = row.heading
        MERGE (d)-[:HAS_CHUNK]->(c)
        """
        self.graphdb.execute_query(query, rows=rows)


    def create_entities_and_relationships_batch(
        self,
        results: list[dict],
        embed_batch_size: int = 1000,
    ) -> tuple[int, int]:
        if not results:
            return 0, 0

        # 1. Prepare entities and texts for embedding
        entity_prepare_rows = []
        for graph in results:
            chunk_id = graph["chunk_id"]
            extracted_text = graph["extracted_text"]
            entities = extracted_text.get("entities", [])
            for idx, entity in enumerate(entities):
                name = entity["entity_name"].strip()
                if not name:
                    continue
                mention_id = f"{chunk_id}_{idx}"
                text = f"{name}. {entity['entity_type']}. {entity['entity_description']}"
                entity_prepare_rows.append({
                    "chunk_id": chunk_id,
                    "mention_id": mention_id,
                    "name": name,
                    "type": entity["entity_type"],
                    "description": entity["entity_description"],
                    "text": text,
                })

        if not entity_prepare_rows:
            return 0, 0

        # 2. Batch embedding
        embeddings = []
        texts_to_embed = [r["text"] for r in entity_prepare_rows]
        for i in range(0, len(texts_to_embed), embed_batch_size):
            batch_texts = texts_to_embed[i : i + embed_batch_size]
            batch_embeddings = self.embedding_model.embed_documents(batch_texts)
            embeddings.extend(batch_embeddings)

        # 3. Build entity rows for Neo4j and build mention_lookups
        entity_rows = []
        mention_lookups = {}
        for row, embedding in zip(entity_prepare_rows, embeddings):
            chunk_id = row["chunk_id"]
            name = row["name"]
            mention_id = row["mention_id"]
            
            entity_rows.append({
                "chunk_id": chunk_id,
                "mention_id": mention_id,
                "name": name,
                "type": row["type"],
                "description": row["description"],
                "embedding": embedding,
            })
            
            if chunk_id not in mention_lookups:
                mention_lookups[chunk_id] = {}
            mention_lookups[chunk_id][self.normalize_name(name)] = mention_id

        # 4. Save entities to Neo4j
        if entity_rows:
            entity_query = """
            UNWIND $rows AS row
            MATCH (c:Chunk {chunk_id: row.chunk_id})
            MERGE (e:EntityMention {mention_id: row.mention_id})
            SET e.name = row.name,
                e.type = row.type,
                e.description = row.description,
                e.frequency = coalesce(e.frequency, 0) + 1,
                e.degree = coalesce(e.degree, 0),
                e.embedding = row.embedding
            MERGE (c)-[:MENTIONS]->(e)
            """
            self.graphdb.execute_query(entity_query, rows=entity_rows)

        # 5. Prepare relationships
        relationship_rows = []
        for graph in results:
            chunk_id = graph["chunk_id"]
            extracted_text = graph["extracted_text"]
            relationships = extracted_text.get("relationships", [])
            mention_lookup = mention_lookups.get(chunk_id, {})
            
            for idx, relationship in enumerate(relationships):
                source = mention_lookup.get(
                    self.normalize_name(relationship["source_entity"])
                )
                target = mention_lookup.get(
                    self.normalize_name(relationship["target_entity"])
                )
                if not source or not target or source == target:
                    continue

                relationship_id = f"{chunk_id}_rel_{idx}"
                relationship_rows.append({
                    "chunk_id": chunk_id,
                    "source": source,
                    "target": target,
                    "relationship_id": relationship_id,
                    "description": relationship["relationship_description"],
                    "weight": float(relationship["relationship_strength"] or 1.0),
                })

        # 6. Save relationships to Neo4j
        if relationship_rows:
            relationship_query = """
            UNWIND $rows AS row
            MATCH (s:EntityMention {mention_id: row.source})
            MATCH (t:EntityMention {mention_id: row.target})
            MERGE (s)-[r:RELATED_TO {relationship_id: row.relationship_id}]->(t)
            SET r.source = row.source,
                r.target = row.target,
                r.description = row.description,
                r.weight = row.weight,
                r.combined_degree = coalesce(r.combined_degree, 0) + 1,
                r.chunk_ids = CASE
                    WHEN r.chunk_ids IS NULL THEN [row.chunk_id]
                    WHEN NOT row.chunk_id IN r.chunk_ids THEN r.chunk_ids + row.chunk_id
                    ELSE r.chunk_ids
                END
            """
            self.graphdb.execute_query(relationship_query, rows=relationship_rows)

        return len(entity_rows), len(relationship_rows)

    def embed_entity(self, entity: Entity) -> list[float]:
        text = f"{entity["entity_name"]}. {entity["entity_type"]}. {entity["entity_description"]}"
        return self.embedding_model.embed_query(text)

    # def build_entity_mention_wcc(
    #     self,
    #     graph_name: str = "entity_mentions",
    #     similarity_cutoff: float = 0.80,
    # ):
    #     # =========================================================
    #     # 1. Drop old GDS projection
    #     # =========================================================

    #     if self.gds.graph.exists(graph_name)["exists"]:
    #         self.gds.graph.drop(graph_name)

    #     # =========================================================
    #     # 2. Project EntityMention
    #     # =========================================================

    #     G, project_result = self.gds.graph.project(
    #         graph_name,
    #         "EntityMention",
    #         "*",
    #         nodeProperties=["embedding"],
    #     )

    #     print(
    #         f"[Entity Resolution] "
    #         f"Projected {project_result}"
    #     )

    #     # =========================================================
    #     # 3. KNN similarity
    #     # =========================================================

    #     knn_result = self.gds.knn.mutate(
    #         G,
    #         nodeProperties=["embedding"],
    #         mutateRelationshipType="SIMILAR",
    #         mutateProperty="score",
    #         similarityCutoff=similarity_cutoff,
    #     )

    #     print(
    #         f"[Entity Resolution] "
    #         f"KNN completed: {knn_result}"
    #     )

    #     # =========================================================
    #     # 4. WCC
    #     # =========================================================

    #     wcc_result = self.gds.wcc.write(
    #         G,
    #         relationshipTypes=["SIMILAR"],
    #         writeProperty="wcc",
    #     )

    #     print(
    #         f"[Entity Resolution] "
    #         f"WCC completed: {wcc_result}"
    #     )

    #     # =========================================================
    #     # 5. Merge EntityMention
    #     #
    #     # Chỉ merge khi:
    #     #
    #     #   - cùng wcc
    #     #   - cùng type
    #     #
    #     # Mỗi group phải có ít nhất 2 EntityMention
    #     # =========================================================

    #     merge_query = """
    #     MATCH (e:EntityMention)
    #     WHERE e.wcc IS NOT NULL
    #     AND e.type IS NOT NULL

    #     WITH
    #         e.wcc AS wcc,
    #         e.type AS entity_type,
    #         collect(e) AS nodes

    #     WHERE size(nodes) > 1

    #     CALL apoc.refactor.mergeNodes(
    #         nodes,
    #         {
    #             properties: {
    #                 `.*`: 'discard'
    #             },
    #             mergeRels: true
    #         }
    #     )
    #     YIELD node

    #     RETURN
    #         wcc,
    #         entity_type,
    #         size(nodes) AS merged_count,
    #         node.mention_id AS canonical_mention_id
    #     """

    #     merge_result = self.gds.run_cypher(
    #         merge_query
    #     )

    #     print(
    #         "[Entity Resolution] "
    #         "EntityMention merge completed:"
    #     )

    #     print(merge_result)

    #     # =========================================================
    #     # 6. Merge duplicate relationships
    #     #
    #     # Sau khi merge node có thể xuất hiện:
    #     #
    #     # A ──RELATED_TO(weight=2)──> B
    #     # A ──RELATED_TO(weight=3)──> B
    #     #
    #     # Kết quả:
    #     #
    #     # A ──RELATED_TO(weight=5)──> B
    #     #
    #     # =========================================================

    #     merge_relationship_query = """
    #     MATCH (a:EntityMention)-[r:RELATED_TO]->(b:EntityMention)

    #     WITH
    #         a,
    #         b,
    #         collect(r) AS relationships

    #     WHERE size(relationships) > 1

    #     WITH
    #         a,
    #         b,
    #         relationships,
    #         reduce(
    #             total = 0.0,
    #             rel IN relationships |
    #             total + coalesce(toFloat(rel.weight), 0.0)
    #         ) AS total_weight

    #     CALL apoc.refactor.mergeRelationships(
    #         relationships,
    #         {
    #             properties: 'discard'
    #         }
    #     )
    #     YIELD rel

    #     SET rel.weight = total_weight

    #     RETURN count(*) AS merged_relationships
    #     """

    #     relationship_result = self.gds.run_cypher(
    #         merge_relationship_query
    #     )

    #     print(
    #         "[Entity Resolution] "
    #         "Relationship merge completed:"
    #     )

    #     print(relationship_result)

    #     # =========================================================
    #     # 7. Get WCC statistics
    #     # =========================================================

    #     stats = self.gds.run_cypher(
    #         """
    #         MATCH (e:EntityMention)
    #         WHERE e.wcc IS NOT NULL

    #         WITH
    #             e.wcc AS community,
    #             e.type AS entity_type,
    #             count(*) AS size

    #         RETURN
    #             community,
    #             entity_type,
    #             size

    #         ORDER BY size DESC
    #         LIMIT 20
    #         """
    #     )

    #     print(
    #         "[Entity Resolution] "
    #         "Top WCC communities:"
    #     )

    #     print(stats)

    #     # =========================================================
    #     # 8. Return result
    #     # =========================================================

    #     return {
    #         "graph": G,
    #         "project": project_result,
    #         "knn": knn_result,
    #         "wcc": wcc_result,
    #         "merge": merge_result,
    #         "relationship_merge": relationship_result,
    #         "stats": stats,
    #     }

    def build_entity_mention_wcc(
        self,
        graph_name: str = "entity_mentions",
        similarity_cutoff: float = 0.90,
        max_cluster_size: int = 100,
        merge_batch_size: int = 100,
    ):
        """
        Entity Resolution pipeline:

        1. Project EntityMention + embeddings
        2. KNN similarity
        3. WCC trên SIMILAR
        4. Merge EntityMention theo (wcc, type)
        5. Chỉ merge cluster có size <= max_cluster_size
        6. Merge duplicate RELATED_TO relationships
        7. Return statistics

        Lưu ý:
        - Không merge các cluster quá lớn để tránh OOM.
        - Không dùng collect() cho toàn bộ graph.
        """

        # =========================================================
        # 1. DROP OLD GDS PROJECTION
        # =========================================================

        if self.gds.graph.exists(graph_name)["exists"]:

            print(
                f"[Entity Resolution] "
                f"Dropping old graph: {graph_name}"
            )

            self.gds.graph.drop(graph_name)


        # =========================================================
        # 2. PROJECT ENTITY MENTION
        # =========================================================

        print(
            "[Entity Resolution] "
            "Projecting EntityMention graph..."
        )

        G, project_result = self.gds.graph.project(
            graph_name,
            "EntityMention",
            "*",
            nodeProperties=["embedding"],
        )

        print(
            "[Entity Resolution] "
            f"Projected: {project_result}"
        )


        # =========================================================
        # 3. KNN SIMILARITY
        # =========================================================

        print(
            "[Entity Resolution] "
            "Running KNN..."
        )

        knn_result = self.gds.knn.mutate(
            G,
            nodeProperties=["embedding"],
            mutateRelationshipType="SIMILAR",
            mutateProperty="score",
            similarityCutoff=similarity_cutoff,
        )

        print(
            "[Entity Resolution] "
            f"KNN completed: {knn_result}"
        )


        # =========================================================
        # 4. WCC
        # =========================================================

        print(
            "[Entity Resolution] "
            "Running WCC..."
        )

        wcc_result = self.gds.wcc.write(
            G,
            relationshipTypes=["SIMILAR"],
            writeProperty="wcc",
        )

        print(
            "[Entity Resolution] "
            f"WCC completed: {wcc_result}"
        )


        # =========================================================
        # 5. WCC STATISTICS
        # =========================================================

        print(
            "[Entity Resolution] "
            "Analyzing WCC clusters..."
        )

        cluster_stats = self.gds.run_cypher(
            """
            MATCH (e:EntityMention)
            WHERE
                e.wcc IS NOT NULL
                AND e.type IS NOT NULL

            RETURN
                e.wcc AS wcc,
                e.type AS entity_type,
                count(*) AS cluster_size

            ORDER BY cluster_size DESC
            """
        )

        print(
            "[Entity Resolution] "
            f"Found {len(cluster_stats)} WCC/type clusters"
        )


        # =========================================================
        # 6. FILTER CLUSTERS
        # =========================================================

        valid_clusters = cluster_stats[
            cluster_stats["cluster_size"] > 1
        ]

        oversized_clusters = valid_clusters[
            valid_clusters["cluster_size"] > max_cluster_size
        ]

        mergeable_clusters = valid_clusters[
            valid_clusters["cluster_size"] <= max_cluster_size
        ]

        print(
            "[Entity Resolution] "
            f"Mergeable clusters: "
            f"{len(mergeable_clusters)}"
        )

        print(
            "[Entity Resolution] "
            f"Oversized clusters skipped: "
            f"{len(oversized_clusters)}"
        )


        # =========================================================
        # 7. MERGE SMALL CLUSTERS
        # =========================================================

        merge_results = []

        for idx, row in mergeable_clusters.iterrows():

            wcc = row["wcc"]
            entity_type = row["entity_type"]
            cluster_size = row["cluster_size"]

            print(
                f"[Entity Resolution] "
                f"Merging cluster "
                f"{idx + 1}/{len(mergeable_clusters)} "
                f"| wcc={wcc} "
                f"| type={entity_type} "
                f"| size={cluster_size}"
            )

            merge_query = """
            MATCH (e:EntityMention)
            WHERE
                e.wcc = $wcc
                AND e.type = $entity_type

            WITH collect(e) AS nodes

            CALL apoc.refactor.mergeNodes(
                nodes,
                {
                    properties: {
                        `.*`: 'discard'
                    },
                    mergeRels: true
                }
            )
            YIELD node

            RETURN
                size(nodes) AS merged_count,
                node.mention_id AS canonical_mention_id
            """

            result = self.gds.run_cypher(
                merge_query,
                params={
                    "wcc": int(wcc),
                    "entity_type": entity_type,
                },
            )

            merge_results.append(result)

        print(
            "[Entity Resolution] "
            "EntityMention merge completed."
        )


        # =========================================================
        # 8. MERGE DUPLICATE RELATED_TO
        # =========================================================

        print(
            "[Entity Resolution] "
            "Merging duplicate RELATED_TO relationships..."
        )

        relationship_result = self.gds.run_cypher(
            """
            MATCH (a:EntityMention)
                -[r:RELATED_TO]->
                (b:EntityMention)

            WITH
                a,
                b,
                collect(r) AS relationships

            WHERE size(relationships) > 1

            WITH
                a,
                b,
                relationships,
                reduce(
                    total = 0.0,
                    rel IN relationships |
                    total + coalesce(
                        toFloat(rel.weight),
                        0.0
                    )
                ) AS total_weight

            CALL apoc.refactor.mergeRelationships(
                relationships,
                {
                    properties: 'discard'
                }
            )
            YIELD rel

            SET rel.weight = total_weight

            RETURN count(*) AS merged_groups
            """
        )

        print(
            "[Entity Resolution] "
            f"Relationship merge completed: "
            f"{relationship_result}"
        )


        # =========================================================
        # 9. FINAL GRAPH STATISTICS
        # =========================================================

        final_stats = self.gds.run_cypher(
            """
            MATCH (e:EntityMention)

            OPTIONAL MATCH (e)-[r:RELATED_TO]-()

            RETURN
                count(DISTINCT e) AS entity_count,
                count(DISTINCT r) AS relationship_count
            """
        )

        print(
            "[Entity Resolution] "
            "Final graph statistics:"
        )

        print(final_stats)


        # =========================================================
        # 10. RETURN
        # =========================================================

        return {
            "graph": G,
            "project": project_result,
            "knn": knn_result,
            "wcc": wcc_result,
            "cluster_stats": cluster_stats,
            "mergeable_clusters": mergeable_clusters,
            "oversized_clusters": oversized_clusters,
            "merge_results": merge_results,
            "relationship_merge": relationship_result,
            "final_stats": final_stats,
        }

    def update_entity(self) -> dict[str, int]:
        """
        Update EntityMention and RELATED_TO relationships
        for chunks that have not been processed yet.

        Pipeline:
            Chunk without EntityMention
                ↓
            Extract entities + relationships
                ↓
            Create EntityMention
                ↓
            Create RELATED_TO
                ↓
            Entity Resolution / WCC
        """

        stats = {
            "chunks": 0,
            "entities": 0,
            "relationships": 0,
            "failed_chunks": 0,
        }

        # =========================================================
        # 1. LOAD CHUNKS WITHOUT ENTITIES
        # =========================================================

        print(
            "[Entity Update] "
            "Loading chunks without extracted entities..."
        )

        result = self.graphdb.execute_query(
            """
            MATCH (c:Chunk)

            WHERE NOT (c)-[:MENTIONS]->(:EntityMention)

            RETURN
                c.chunk_id AS chunk_id,
                c.url AS url,
                c.title AS title,
                c.heading AS heading,
                c.chunk_text AS chunk_text
            """
        )

        chunks = []

        for record in result.records:
            chunks.append(
                {
                    "chunk_id": record["chunk_id"],
                    "url": record["url"],
                    "title": record["title"],
                    "heading": record["heading"],
                    "chunk_text": record["chunk_text"],
                }
            )

        stats["chunks"] = len(chunks)

        print(
            f"[Entity Update] "
            f"Found {len(chunks)} chunks to process"
        )

        if not chunks:
            print(
                "[Entity Update] "
                "No new chunks need entity extraction."
            )
            return stats

        # =========================================================
        # 2. EXTRACT ENTITY + RELATIONSHIP
        # =========================================================

        results = []

        print(
            f"[Entity Update] "
            f"Extracting entities from {len(chunks)} chunks..."
        )

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            futures = {
                executor.submit(
                    self.extract_graph,
                    idx,
                    chunk,
                ): chunk["chunk_id"]
                for idx, chunk in enumerate(chunks)
            }

            total = len(futures)

            for completed, future in enumerate(
                as_completed(futures),
                start=1,
            ):

                chunk_id = futures[future]

                try:

                    graph = future.result()

                    if graph:
                        results.append(graph)

                    else:
                        stats["failed_chunks"] += 1

                        print(
                            f"[Entity Update] "
                            f"Chunk {chunk_id} extraction failed"
                        )

                except Exception as e:

                    stats["failed_chunks"] += 1

                    print(
                        f"[Entity Update] "
                        f"Chunk {chunk_id} failed: {e}"
                    )

                print(
                    f"[Entity Update] "
                    f"Processed {completed}/{total}"
                )

        # =========================================================
        # 3. CREATE ENTITIES + RELATIONSHIPS
        # =========================================================

        print(
            f"[Entity Update] "
            f"Saving {len(results)} extracted chunks..."
        )

        batch_size = 5000
        for i in range(0, len(results), batch_size):
            results_batch = results[i : i + batch_size]
            entities_count, relationships_count = self.create_entities_and_relationships_batch(results_batch)
            stats["entities"] += entities_count
            stats["relationships"] += relationships_count

        # =========================================================
        # 4. UPDATE ENTITY RESOLUTION
        # =========================================================

        if stats["entities"] > 0:

            print(
                "[Entity Update] "
                "Rebuilding Entity Resolution..."
            )

            self.build_entity_mention_wcc()

        # =========================================================
        # 5. SUMMARY
        # =========================================================

        print(
            "[Entity Update] Completed: "
            f"chunks={stats['chunks']}, "
            f"entities={stats['entities']}, "
            f"relationships={stats['relationships']}, "
            f"failed={stats['failed_chunks']}"
        )

        return stats


    def update_communities(
        self,
        graph_name: str = "entity_graph",
    ):
        # =========================================================
        # 1. Removing old communities
        # =========================================================

        print("[Community] Removing old communities...")

        result = self.graphdb.execute_query(
            """
            MATCH (c:Community)
            DETACH DELETE c
            RETURN count(c) AS deleted
            """
        )

        deleted = result.records[0]["deleted"]

        print(
            f"[Community] "
            f"Deleted {deleted} old communities"
        )

        # =========================================================
        # 2. PROJECT GRAPH FOR LEIDEN
        # =========================================================

        if self.gds.graph.exists(graph_name)["exists"]:
            self.gds.graph.drop(graph_name)

        G, project_result = self.gds.graph.project(
            "entity_graph",
            "EntityMention",
            {
                "RELATED_TO": {
                    "orientation": "UNDIRECTED",
                    "properties": "weight"
                }
            },
        )

        print(
            f"[Community] "
            f"Graph projected: {project_result}"
        )

        # =========================================================
        # 3. RUN LEIDEN
        # =========================================================

        leiden_result = self.gds.leiden.write(
            G,
            relationshipWeightProperty="weight",
            writeProperty="communities",
            includeIntermediateCommunities=True,
            maxLevels=3,
        )

        print(
            "[Community] "
            f"Leiden completed: {leiden_result}"
        )

        # =========================================================
        # 4. [Community] Creating communities
        # =========================================================

        print("[Community] Creating communities...")

        result = self.graphdb.execute_query(
            """
            MATCH (e:EntityMention)
            WHERE e.communities IS NOT NULL
            AND size(e.communities) > 0

            UNWIND range(0, size(e.communities) - 1) AS level

            WITH DISTINCT
                level,
                e.communities[level] AS leiden_id

            MERGE (c:Community {
                community_id:
                    toString(level) + "-" + toString(leiden_id)
            })

            SET
                c.level = level,
                c.leiden_community_id = leiden_id,
                c.is_active = true,
                c.updated_at = datetime()

            RETURN count(*) AS communities
            """
        )
        result = self.graphdb.execute_query(
            """
            MATCH (e:EntityMention)
            WHERE e.communities IS NOT NULL
            AND size(e.communities) > 0

            UNWIND range(0, size(e.communities) - 1) AS level

            WITH
                e,
                level,
                e.communities[level] AS leiden_id

            MATCH (c:Community {
                community_id:
                    toString(level) + "-" + toString(leiden_id)
            })

            MERGE (e)-[:IN_COMMUNITY]->(c)

            RETURN count(*) AS entity_community_links
            """
        )



        count = result.records[0]["entity_community_links"]

        print(
            f"[Community] "
            f"Created/updated {count} entity-community links"
        )

        # =========================================================
        # 5. [Community] Creating community hierarchy...
        # =========================================================

        print("[Community] Creating community hierarchy...")

        result = self.graphdb.execute_query(
            """
            MATCH (e:EntityMention)

            WHERE e.communities IS NOT NULL
                AND size(e.communities) > 1

            UNWIND range(1, size(e.communities) - 1) AS level

            WITH
                level,
                e.communities[level - 1] AS parent_leiden_id,
                e.communities[level] AS child_leiden_id

            MATCH (parent:Community {
                community_id:
                    toString(level - 1)
                    + "-"
                    + toString(parent_leiden_id)
            })

            MATCH (child:Community {
                community_id:
                    toString(level)
                    + "-"
                    + toString(child_leiden_id)
            })

            MERGE (parent)-[:PARENT_OF]->(child)

            RETURN count(*) AS hierarchy_links
            """
        )

        count = result.records[0]["hierarchy_links"]

        print(
            f"[Community] "
            f"Created {count} community hierarchy links"
        )
        # =====================================================
        # NEW COMMUNITY
        # =====================================================

        """
        Generate / update report cho toàn bộ Community.

        Pipeline:

            Community
                ↓
            Load EntityMention
                ↓
            Load RELATED_TO
                ↓
            Build context
                ↓
            LLM Generate Report
                ↓
            Generate Summary Embedding
                ↓
            Save Community
        """

        # =========================================================
        # LOAD ALL COMMUNITIES
        # =========================================================

        print("[Community] Loading communities...")

        communities_result = self.graphdb.execute_query(
            """
            MATCH (c:Community)

            RETURN
                c.community_id AS community_id,
                c.level AS level,
                c.leiden_community_id AS leiden_community_id
            ORDER BY
                c.level,
                c.community_id
            """
        )

        communities = []

        for record in communities_result.records:

            communities.append(
                {
                    "community_id": record["community_id"],
                    "level": record["level"],
                    "leiden_community_id": (
                        record["leiden_community_id"]
                    ),
                }
            )

        print(
            f"[Community] "
            f"Found {len(communities)} communities"
        )

        updated_reports = []

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            futures = {
                executor.submit(
                    self.process_community,
                    community,
                ): community["community_id"]
                for community in communities
            }

            total = len(futures)

            for completed, future in enumerate(
                as_completed(futures),
                start=1,
            ):

                community_id = futures[future]

                try:

                    result = future.result()

                    if result:
                        updated_reports.append(
                            result
                        )

                except Exception as e:

                    print(
                        f"[Community] "
                        f"Community {community_id} "
                        f"failed: {e}"
                    )

                print(
                    f"[Community] "
                    f"Progress: "
                    f"{completed}/{total}"
                )

        print(
            f"[Community] "
            f"Updated {len(updated_reports)} "
            f"community reports"
        )

        return updated_reports

    def update_communities_big_context(self):
        """
        Generate Community Reports for communities that do not have
        a valid report yet.

        Pipeline:

            Community without report
                ↓
            Load EntityMention
                ↓
            Load RELATED_TO
                ↓
            Build large context
                ↓
            LLM Generate Report
                ↓
            Generate Summary Embedding
                ↓
            Save Community Report
        """

        # =========================================================
        # 1. LOAD COMMUNITIES WITHOUT REPORT
        # =========================================================

        print(
            "[Community Big Context] "
            "Loading communities without reports..."
        )

        communities_result = self.graphdb.execute_query(
            """
            MATCH (c:Community)

            WHERE
                c.summary IS NULL
                OR trim(c.summary) = ""
                OR c.embedding IS NULL

            RETURN
                c.community_id AS community_id,
                c.level AS level,
                c.leiden_community_id AS leiden_community_id

            ORDER BY
                c.level,
                c.community_id
            """
        )

        communities = []

        for record in communities_result.records:

            communities.append(
                {
                    "community_id": record["community_id"],
                    "level": record["level"],
                    "leiden_community_id": (
                        record["leiden_community_id"]
                    ),
                }
            )

        print(
            f"[Community Big Context] "
            f"Found {len(communities)} communities "
            f"without reports"
        )

        if not communities:
            print(
                "[Community Big Context] "
                "No communities need updating."
            )

            return []

        # =========================================================
        # 2. PROCESS COMMUNITIES IN PARALLEL
        # =========================================================

        updated_reports = []

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            futures = {
                executor.submit(
                    self.process_community,
                    community,
                ): community["community_id"]
                for community in communities
            }

            total = len(futures)

            for completed, future in enumerate(
                as_completed(futures),
                start=1,
            ):

                community_id = futures[future]

                try:

                    result = future.result()

                    if result:

                        updated_reports.append(
                            result
                        )

                except Exception as e:

                    print(
                        f"[Community Big Context] "
                        f"Community {community_id} "
                        f"failed: {e}"
                    )

                print(
                    f"[Community Big Context] "
                    f"Progress: "
                    f"{completed}/{total}"
                )

        # =========================================================
        # 3. SUMMARY
        # =========================================================

        print(
            f"[Community Big Context] "
            f"Updated {len(updated_reports)} "
            f"community reports"
        )

        return updated_reports


    def process_community(self, community):

        community_id = community["community_id"]
        level = community["level"]

        print(
            f"[Community] Processing "
            f"{community_id} "
            f"(level={level})"
        )

        # =====================================================
        # 2.1 LOAD ENTITIES
        # =====================================================

        entities_result = self.graphdb.execute_query(
            """
            MATCH (e:EntityMention)
                -[:IN_COMMUNITY]->
                (c:Community)

            WHERE c.community_id = $community_id

            RETURN
                e.mention_id AS mention_id,
                e.name AS name,
                e.type AS type,
                e.description AS description
            """,
            community_id=community_id,
        )

        entity_context = []

        for record in entities_result.records:

            entity_context.append(
                {
                    "mention_id": record["mention_id"],
                    "name": record["name"],
                    "type": record["type"],
                    "description": (
                        record["description"]
                        or ""
                    ),
                }
            )

        if not entity_context:

            print(
                f"[Community] "
                f"{community_id} has no entities"
            )

            return None

        # =====================================================
        # 2.2 LOAD RELATIONSHIPS
        # =====================================================

        relationships_result = self.graphdb.execute_query(
            """
            MATCH (a:EntityMention)
                -[r:RELATED_TO]->
                (b:EntityMention)

            MATCH (a)-[:IN_COMMUNITY]->(c:Community)

            MATCH (b)-[:IN_COMMUNITY]->(c)

            WHERE c.community_id = $community_id

            RETURN
                a.name AS source,
                b.name AS target,
                r.description AS description,
                r.weight AS weight
            """,
            community_id=community_id,
        )

        relationship_context = []

        for record in relationships_result.records:

            relationship_context.append(
                {
                    "source": record["source"],
                    "target": record["target"],
                    "description": (
                        record["description"]
                        or ""
                    ),
                    "weight": (
                        record["weight"]
                        or 1.0
                    ),
                }
            )

        # =====================================================
        # 2.3 BUILD COMMUNITY CONTEXT
        # =====================================================

        community_context = {
            "community_id": community_id,
            "level": level,
            "entities": entity_context,
            "relationships": relationship_context,
        }

        print(
            f"[Community] {community_id}: "
            f"{len(entity_context)} entities, "
            f"{len(relationship_context)} relationships"
        )

        # =====================================================
        # 2.4 GENERATE REPORT
        # =====================================================

        # Nếu chỉ có 1 entity thì không cần gọi LLM
        if len(entity_context) == 1:

            entity = entity_context[0]

            report = CommunityReport(
                title=entity["name"],
                summary=(
                    entity["description"]
                    or entity["name"]
                ),
                key_entities=[
                    entity["name"]
                ],
                key_relationships=[],
                findings=[
                    entity["description"]
                ] if entity["description"] else [],
            )

            print(
                f"[Community] "
                f"{community_id}: "
                f"single entity, skip LLM"
            )

        else:

            report = self.generate_community_report(
                community_context
            )

            if not report:

                print(
                    f"[Community] "
                    f"Failed to generate report: "
                    f"{community_id}"
                )

                return None

        # =====================================================
        # 2.5 GENERATE EMBEDDING
        # =====================================================

        summary_embedding = (
            self.embedding_model.embed_query(
                report.summary
            )
        )

        # =====================================================
        # 2.6 SAVE COMMUNITY REPORT
        # =====================================================

        self.graphdb.execute_query(
            """
            MATCH (c:Community {
                community_id: $community_id
            })

            SET
                c.level = $level,
                c.title = $title,
                c.summary = $summary,
                c.key_entities = $key_entities,
                c.key_relationships = $key_relationships,
                c.findings = $findings,
                c.embedding = $embedding,
                c.is_active = true,
                c.updated_at = datetime()

            RETURN
                c.community_id AS community_id
            """,
            community_id=community_id,
            level=level,
            title=report.title,
            summary=report.summary,
            key_entities=report.key_entities,
            key_relationships=(
                report.key_relationships
            ),
            findings=report.findings,
            embedding=summary_embedding,
        )

        return {
            "community_id": community_id,
            "level": level,
            "entity_count": len(
                entity_context
            ),
            "relationship_count": len(
                relationship_context
            ),
        }

    def generate_community_report(
        self,
        community_context: dict,
    ) -> CommunityReport | None:

        try:

            prompt = f"""
    You are an expert in medical knowledge graph analysis.

    Analyze the following community of medical entities
    and relationships.

    Generate a concise and factual community report.

    Community:
    {json.dumps(
        community_context,
        ensure_ascii=False,
        indent=2,
    )}

    Rules:
    - Use only information provided in the community.
    - Do not invent medical facts.
    - Identify the main topic.
    - Summarize important entities and relationships.
    - Focus on medically meaningful information.
    """


            
            response = self.structured_llm_community_report.invoke(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are an expert in "
                            "medical knowledge graph analysis."
                        ),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ]
            )

            return response

        except Exception as e:

            print(
                "[Community Report] "
                f"Failed to generate report: {e}"
            )

            return None


    @staticmethod
    def normalize_text(text: Any) -> str:
        return " ".join(str(text or "").split())

    @staticmethod
    def normalize_name(name: str) -> str:
        return " ".join(str(name or "").lower().split())

    @staticmethod
    def first_value(row: dict[str, Any], keys: list[str]) -> str:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    # @staticmethod
    # def make_id(*parts: str) -> str:
    #     raw = "||".join(str(part) for part in parts)
    #     return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def detect_file_type(source_type: Any) -> str:
        source_type = str(source_type or "").lower()
        if source_type in {"csv", "pdf"}:
            return source_type

        return "other"



import_document = ImportDocument()
