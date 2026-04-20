# TASK-003: Memory System Implementation (3-Tier)

## Metadata
- **Task ID**: TASK-003
- **Title**: Memory System Implementation (3-Tier)
- **Assigned To**: Code
- **Mode**: strict
- **Created**: 2026-04-20
- **Dependencies**: TASK-002 (Core Agent Architecture)

## Description
Implement the 3-tier memory system: persistent configuration, short-term context management with compaction strategies, and long-term vector storage. Replace JSON state with sqlite3 for atomic transactions and integrity.

## Acceptance Criteria
1. **Persistent Memory**: `agent.md` reading/writing with structured sections
2. **Short-term Memory**: Context window management with:
   - Token tracking
   - `snip` strategy (trim oldest context when limit exceeded)
   - `microcompact` strategy (summarize trimmed context)
3. **Long-term Memory**: Vector DB integration interface (FAISS or ChromaDB local)
4. **State Database**: sqlite3 backend with tables: `sessions`, `steps`, `context_chunks`
5. Atomic transactions for all state modifications
6. Context isolation: separate storage for memory, tool output, instructions

## DoD (Definition of Done)
- [ ] sqlite3 database implemented with schema: `sessions`, `steps`, `context_chunks`
- [ ] All database operations use atomic transactions
- [ ] Context manager class with token tracking
- [ ] `snip` strategy implemented and tested (trim + verify)
- [ ] `microcompact` strategy implemented (summarize via LLM call)
- [ ] Vector DB interface abstract class defined (FAISS and ChromaDB adapters)
- [ ] Context isolation: memory, tool output, instructions stored separately
- [ ] State persistence: save/restore full agent state to sqlite3
- [ ] Unit tests cover: database operations, context compaction, state serialization
- [ ] Reviewer approval (PASS or PASS_WITH_NOTES on REVIEW_REPORT)

## Implementation Notes
- Database path: `.ceh_state.db` in project root
- Schema:
  ```sql
  CREATE TABLE sessions (id TEXT PRIMARY KEY, created_at INTEGER, metadata TEXT);
  CREATE TABLE steps (id TEXT PRIMARY KEY, session_id TEXT, step_number INTEGER, role TEXT, content TEXT, timestamp INTEGER);
  CREATE TABLE context_chunks (id TEXT PRIMARY KEY, session_id TEXT, chunk_type TEXT, content TEXT, token_count INTEGER);
  ```
- Context compaction should be triggered when context reaches 80% of max window
- Vector DB integration should be optional — agent works without it
- Use `pydantic` for all data models
- Context isolation: `chunk_type` in `context_chunks` table distinguishes memory/tool/instruction
