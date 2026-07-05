from datetime import datetime, timezone
# Typing
from typing import Optional, Dict, List, Literal, Any
# Schema
from app.schemas.runs import RunStatus
# Exception
from app.exceptions.threads import ThreadNotFoundException
from app.exceptions.runs import RunNotFoundException
# Other components
from app.db.postgres.thread_store import _check_thread_exists
import asyncpg, json

# Common SELECT field group for run queries
RUN_SELECT_FIELDS = """
    r.id,
    'thread.run' AS object,
    EXTRACT(EPOCH FROM r.created_at)::BIGINT AS created_at,
    r.assistant_id,
    r.thread_id,
    r.status,
    EXTRACT(EPOCH FROM r.started_at)::BIGINT AS started_at,
    EXTRACT(EPOCH FROM r.completed_at)::BIGINT AS completed_at,
    EXTRACT(EPOCH FROM r.failed_at)::BIGINT AS failed_at,
    EXTRACT(EPOCH FROM r.cancelled_at)::BIGINT AS cancelled_at,
    a.model,
    a.instructions,
    a.metadata AS assistant_metadata,
    r.metadata AS run_metadata,
    r.usage AS usage,
    r.max_prompt_tokens,
    r.max_completion_tokens,
    a.response_format,
    'auto' AS tool_choice,
    TRUE AS parallel_tool_calls
"""

class PostgresRunStore:
    @staticmethod
    async def create_run(pool: asyncpg.Pool,
                         thread_id: str,
                         run_id: str,
                         assistant_id: str,
                         max_prompt_tokens: Optional[int] = None,
                         max_completion_tokens: Optional[int] = None) -> str:
        """
        Create a new run record in the database.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread this run belongs to
            run_id: Unique identifier for the new run
            assistant_id: ID of the assistant handling this run
            max_prompt_tokens: Maximum allowed prompt tokens (optional)
            max_completion_tokens: Maximum allowed completion tokens (optional)
            
        Returns:
            str: The ID of the created run (same as input run_id)
            
        Note:
            New runs are automatically created with 'queued' status.
        """
        # SQL query to insert new run with queued status
        query = """
            INSERT INTO runs (
                id, thread_id, assistant_id, status,
                max_prompt_tokens, max_completion_tokens
            )
            VALUES ($1, $2, $3, 'queued', $4, $5)
        """
        
        # Execute query using connection from pool
        async with pool.acquire() as conn:
            await conn.execute(query, run_id, thread_id, assistant_id,
                               max_prompt_tokens, max_completion_tokens)
        
        return run_id

    @staticmethod
    async def update_run_status(pool: asyncpg.Pool,
                                run_id: str,
                                status: RunStatus = RunStatus.IN_PROGRESS) -> None:
        """
        Update run status and automatically set corresponding timestamp.

        Args:
            pool: PostgreSQL connection pool
            run_id: ID of the run to update
            status: New status to set (defaults to IN_PROGRESS)

        Returns:
            None

        Note:
            Certain status transitions automatically set timestamps:
            - IN_PROGRESS → started_at
            - COMPLETED → completed_at
            - FAILED → failed_at
            - CANCELED → cancelled_at
        """
        # Get current UTC timestamp for consistent timekeeping
        now = datetime.now(timezone.utc)

        # Mapping of status transitions to their corresponding timestamp fields
        field_map = {
            RunStatus.IN_PROGRESS: "started_at",
            RunStatus.COMPLETED: "completed_at",
            RunStatus.FAILED: "failed_at",
            RunStatus.CANCELED: "cancelled_at",
        }
        time_field = field_map.get(status)

        # Execute update using connection from pool
        async with pool.acquire() as conn:
            if time_field:
                # Update both status and corresponding timestamp
                query = f"""
                UPDATE runs
                SET status = $2, {time_field} = $3
                WHERE id = $1
                """
                await conn.execute(query, run_id, status, now)
            else:
                # Update status only (for statuses without timestamps)
                query = "UPDATE runs SET status = $2 WHERE id = $1"
                await conn.execute(query, run_id, status)

    @staticmethod
    async def update_run_usage(pool: asyncpg.Pool,
                               run_id: str,
                               usage: Dict) -> None:
        """
        Update token usage statistics for a given run.
        
        Args:
            pool: PostgreSQL connection pool
            run_id: ID of the run to update
            usage: Dictionary containing token usage data
                  (prompt_tokens, completion_tokens, total_tokens)
            
        Returns:
            None
            
        Note:
            Usage data is stored as JSONB in the database for flexible querying.
        """
        # SQL query to update usage field as JSONB
        query = """
        UPDATE runs
        SET usage = $2::jsonb
        WHERE id = $1
        """
        
        # Convert usage dict to JSON string and execute update
        async with pool.acquire() as conn:
            await conn.execute(query, run_id, json.dumps(usage))

    @staticmethod
    async def get_runs(pool: asyncpg.Pool,
                       thread_id: str,
                       after: Optional[str] = None,
                       before: Optional[str] = None,
                       limit: int = 20,
                       order: Literal["asc", "desc"] = "desc") -> List[Dict[str, Any]]:
        """
        Retrieve runs for a given thread with cursor-based pagination.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread to fetch runs from
            after: Cursor ID to fetch runs after this point (optional)
            before: Cursor ID to fetch runs before this point (optional)
            limit: Maximum number of runs to return (default: 20, max: 100)
            order: Sort order - "asc" or "desc" (default: "desc")
            
        Returns:
            List[Dict[str, Any]]: List of run objects with assistant metadata
            
        Raises:
            ThreadNotFoundException: If the specified thread_id does not exist
            
        Note:
            Supports cursor-based pagination for efficient data retrieval.
            Returns runs sorted by creation timestamp.
        """

        # Validate and sanitize input parameters
        limit = max(1, min(limit, 100))  # Clamp limit between 1 and 100
        order = order.lower()
        if order not in ("asc", "desc"):
            order = "desc"  # Default to descending order

        # Build WHERE conditions dynamically for pagination
        conditions = ["r.thread_id = $1"]
        params = [thread_id]
        idx = 2

        # Add cursor-based pagination conditions (seq, not created_at: see messages.seq)
        if after:
            # Fetch runs created after the specified cursor
            conditions.append(f"r.seq > (SELECT seq FROM runs WHERE id = ${idx})")
            params.append(after)
            idx += 1

        if before:
            # Fetch runs created before the specified cursor
            conditions.append(f"r.seq < (SELECT seq FROM runs WHERE id = ${idx})")
            params.append(before)
            idx += 1

        where_clause = " AND ".join(conditions)

        # Build final query with pagination and sorting
        query = f"""
            SELECT
                {RUN_SELECT_FIELDS}
            FROM runs r
            LEFT JOIN assistants a ON r.assistant_id = a.assistant_id
            WHERE {where_clause}
            ORDER BY r.seq {order}
            LIMIT ${idx}
        """
        params.append(limit)

        # Execute query with connection from pool
        async with pool.acquire() as conn:
            # Verify thread exists before fetching runs
            if not await _check_thread_exists(conn, thread_id):
                raise ThreadNotFoundException(thread_id=thread_id)
            
            # Fetch and return runs
            rows = await conn.fetch(query, *params)
            
        # Convert asyncpg Record objects to dictionaries
        return [dict(row) for row in rows]

    @staticmethod
    async def get_run(pool: asyncpg.Pool,
                      thread_id: str,
                      run_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single run by its ID and thread ID.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread containing the run
            run_id: ID of the run to retrieve
            
        Returns:
            Dict[str, Any]: Run object with assistant metadata and JSON fields
            
        Raises:
            ThreadNotFoundException: If the specified thread_id does not exist
            RunNotFoundException: If the specified run_id does not exist
            
        Note:
            Returns complete run information including assistant metadata
            and properly formatted JSON fields.
        """
        # Define join clause for assistant metadata
        RUN_JOIN_ASSISTANT = "LEFT JOIN assistants a ON r.assistant_id = a.assistant_id"
        
        # Build query to fetch single run with assistant information
        query = f"""
            SELECT {RUN_SELECT_FIELDS}
            FROM runs r
            {RUN_JOIN_ASSISTANT}
            WHERE r.id = $1 AND r.thread_id = $2
            LIMIT 1
        """

        # Execute query using connection from pool
        async with pool.acquire() as conn:
            # Verify thread exists before fetching run
            if not await _check_thread_exists(conn, thread_id):
                raise ThreadNotFoundException(thread_id=thread_id)
            
            # Fetch the specific run
            row = await conn.fetchrow(query, run_id, thread_id)

        # Check if run was found
        if not row:
            raise RunNotFoundException(run_id=run_id)

        # Convert asyncpg Record object to dictionary and return
        return dict(row)



