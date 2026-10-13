# ROXY-AI — POST-PHASE 5.1: KNOWLEDGE, MEMORY & CONVERSATIONS AUDIT
*(Workstream L Deliverable)*

## 1. Knowledge Vault & RAG Pipeline

Roxy-AI's Retrieval-Augmented Generation (RAG) subsystem operates through [KnowledgeVault.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/KnowledgeVault/KnowledgeVault.tsx) and [backend/src/app/vault/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/vault/):

- **Supported File Types:** PDF, TXT, Markdown, CSV, DOCX (validated by MIME check; executable binaries rejected).
- **Chunking Strategy:** Recursive text splitter (500 tokens per chunk with 50-token overlap).
- **Storage & Vector Index:** Chunk metadata stored in PostgreSQL `document_vault` table with pgvector embeddings.
- **Tenant Isolation:** Every SQL query includes `WHERE user_id = :current_user_id`; cross-tenant document leakage is strictly prevented.

---

## 2. Long-Term Semantic Memory & Personalization

The memory extraction engine ([backend/src/app/memory/](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/backend/src/app/memory/) & [MemoryStudio.tsx](file:///d:/USER/Documents/alibaba-ai-hacathon-chatbot/roxy-personal-ai/frontend/src/components/MemoryStudio/MemoryStudio.tsx)) automatically extracts user facts, constraints, and preferences:

| Memory Operation | Mechanism | Safety & Privacy Boundary | Verification |
| :--- | :--- | :--- | :---: |
| **Fact Extraction** | Parses completed conversations for persistent user facts (e.g. "User prefers TypeScript") | User can inspect and delete every extracted fact in Memory Studio | **PASS** |
| **Context Injection**| Injects relevant memories into system prompt before model dispatch | Token budget capped at 1,500 tokens to prevent context dilution | **PASS** |
| **Memory Deletion** | Delete button permanently purges fact from `semantic_memory` table | Immediately deleted; verified absent from subsequent prompt contexts | **PASS** |
| **Personalization** | Personalization service in `app.personalization.service` | Defaults `preferred_models` to `["gemini-3.8-flash"]` | **PASS** |

---

## 3. Test Verification Evidence

- `backend/tests/integration/test_phase6_knowledge_vault_semantic_memory.py`: Document upload, text chunking, semantic retrieval, and tenant isolation (**PASS (8/8)**).
- `backend/tests/integration/test_phase18_memory.py`: Fact extraction, retrieval score ranking, and manual deletion (**PASS**).
- Zero memory leakage observed between separate test user accounts.
