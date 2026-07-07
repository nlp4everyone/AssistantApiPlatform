# Typing
from typing import Dict, Any, Optional, List, Literal
# Exception
from app.exceptions.messages import MessageNotFoundException
from app.exceptions.threads import ThreadNotFoundException
# Other components
from app.db.postgres.existence import check_row_exists
import asyncpg, json

class PostgresMessageStore:
    """PostgreSQL database operations for message storage and retrieval.
    
    This class provides static methods for CRUD operations on messages
    stored in a PostgreSQL database, including thread validation and
    data formatting.
    """
    @staticmethod
    async def insert_messages(pool: asyncpg.Pool,
                              thread_id: str,
                              data: Dict[str, List[Dict[str,Any]]]) -> None:
        """Insert one or more messages into a thread.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread to insert messages into
            data: Dictionary containing message data with 'data' key holding list of messages
                 Optional keys: 'run_id', 'metadata', 'assistant_id'
        
        Raises:
            ThreadNotFoundException: If the specified thread doesn't exist
            asyncpg.PostgresError: If database operation fails
        """
        query = """
            INSERT INTO messages (
                id, thread_id, role, run_id,
                content, metadata, attachments, assistant_id
            )
            VALUES (
                $1, $2, $3, $4,
                $5::jsonb, $6::jsonb, $7::jsonb, $8
            )
            RETURNING id;
        """
        # Extract messages from data payload
        messages_data = data.get("data")

        # Handle single message insertion
        if len(messages_data) == 1:
            # Get the single message object
            messages_data = messages_data[0]
            # Execute single message insertion
            async with pool.acquire() as conn:
                # Verify thread exists before inserting
                if not await check_row_exists(conn, "threads", "id", thread_id):
                    raise ThreadNotFoundException(id = thread_id)

                # Insert the message and return its ID
                inserted_id = await conn.fetchval(
                    query,
                    messages_data.get("id"),
                    thread_id,
                    messages_data.get("role", "user"),
                    data.get("run_id"),
                    json.dumps(messages_data.get("content")[0]),
                    json.dumps(data.get("metadata", {})),
                    json.dumps(data.get("attachments", [])),
                    data.get("assistant_id"),
                )
        else:
            # Handle multiple message insertion
            rows = []
            # Prepare batch data for all messages
            for msg in messages_data:
                rows.append((
                    msg.get("id"),
                    thread_id,
                    msg.get("role", "user"),
                    data.get("run_id"),
                    json.dumps(msg.get("content")[0]),
                    json.dumps(msg.get("metadata", {})),
                    json.dumps(msg.get("attachments", [])),
                    data.get("assistant_id"),
                ))
            # Execute batch insertion
            async with pool.acquire() as conn:
                # Verify thread exists before inserting
                if not await check_row_exists(conn, "threads", "id", thread_id):
                    raise ThreadNotFoundException(id = thread_id)

                # Insert all messages in a single transaction
                await conn.executemany(query, rows)

    @staticmethod
    async def get_thread_messages(pool: asyncpg.Pool,
                                  thread_id: str,
                                  after: Optional[str] = None,
                                  before: Optional[str] = None,
                                  limit: int = 20,
                                  order: Literal["desc","asc"] = "desc",
                                  run_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch messages belonging to a thread with filters and pagination.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread to fetch messages from
            after: Optional message ID to fetch messages after (chronological)
            before: Optional message ID to fetch messages before (chronological)
            limit: Maximum number of messages to return (default: 20)
            order: Sort order - "asc" for oldest first, "desc" for newest first (default: "desc")
            run_id: Optional run ID to filter messages by specific run
        
        Returns:
            List of message dictionaries with raw database fields
        
        Raises:
            ThreadNotFoundException: If the specified thread doesn't exist
            asyncpg.PostgresError: If database operation fails
        """
        # Validate and normalize sort order
        if order.lower() not in ("asc", "desc"):
            order = "desc"

        # Build dynamic WHERE conditions based on provided filters
        conditions = ["m.thread_id = $1"]
        params = [thread_id]
        idx = 2  # Track parameter index for prepared statement

        # Add run_id filter if specified
        if run_id:
            conditions.append(f"m.run_id = ${idx}")
            params.append(run_id)
            idx += 1

        # Add 'after' cursor filter if specified (seq, not created_at: batch inserts
        # share one created_at since now() is transaction-scoped, which breaks ordering/pagination)
        if after:
            conditions.append(f"m.seq > (SELECT seq FROM messages WHERE id = ${idx})")
            params.append(after)
            idx += 1

        # Add 'before' cursor filter if specified
        if before:
            conditions.append(f"m.seq < (SELECT seq FROM messages WHERE id = ${idx})")
            params.append(before)
            idx += 1

        # Combine all conditions into WHERE clause
        where_clause = " AND ".join(conditions)

        # Build final query with dynamic filters and ordering
        query = f"""
                SELECT m.*
                FROM messages m
                WHERE {where_clause}
                ORDER BY m.seq {order}
                LIMIT ${idx}
                """

        # Add limit parameter to params list
        params.append(limit)
        async with pool.acquire() as conn:
            # Verify thread exists before fetching messages
            if not await check_row_exists(conn, "threads", "id", thread_id):
                raise ThreadNotFoundException(id = thread_id)
            # Execute query and fetch all matching rows
            rows = await conn.fetch(query, *params)

        return [dict(row) for row in rows]

    @staticmethod
    async def get_message_by_id(pool: asyncpg.Pool,
                                thread_id: str,
                                message_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific message by its ID within a thread.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread containing the message
            message_id: ID of the specific message to retrieve
        
        Returns:
            Message dictionary with processed JSON fields and Unix timestamp
        
        Raises:
            ThreadNotFoundException: If the specified thread doesn't exist
            MessageNotFoundException: If the specified message doesn't exist
            asyncpg.PostgresError: If database operation fails
        """
        # Query to fetch specific message by thread and message ID
        query = "SELECT * FROM messages WHERE thread_id=$1 AND id=$2"
        async with pool.acquire() as conn:
            # Verify thread exists before fetching message
            if not await check_row_exists(conn, "threads", "id", thread_id):
                raise ThreadNotFoundException(id = thread_id)
            # Fetch the specific message
            row = await conn.fetchrow(query, thread_id, message_id)
            # Raise error if message not found
            if row is None: raise MessageNotFoundException(id = message_id)

        # Convert database row to dictionary
        row = dict(row)
        # Convert timestamp to Unix timestamp (seconds since epoch)
        created_at = row.get("created_at")
        row.update({"created_at": int(created_at.timestamp())})
        # Parse JSON fields from database storage
        row.update({"metadata": json.loads(row.get("metadata"))})
        row.update({"attachments": json.loads(row.get("attachments"))})
        # Parse content JSON and wrap in list for API compatibility
        row.update({"content": [json.loads(row.get("content"))]})
        return row

    @staticmethod
    async def delete_message(pool: asyncpg.Pool,
                             thread_id: str,
                             message_id: str) -> None:
        """Delete a specific message from a thread.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: ID of the thread containing the message
            message_id: ID of the message to delete
        
        Raises:
            ThreadNotFoundException: If the specified thread doesn't exist
            MessageNotFoundException: If the specified message doesn't exist
            asyncpg.PostgresError: If database operation fails
        """
        # Query to delete specific message by thread and message ID
        query = "DELETE FROM messages WHERE thread_id=$1 AND id=$2"
        async with pool.acquire() as conn:
            # Verify thread exists before deleting message
            if not await check_row_exists(conn, "threads", "id", thread_id):
                raise ThreadNotFoundException(id = thread_id)
            # Execute deletion and check result
            result = await conn.execute(query, thread_id, message_id)
            # PostgreSQL returns 'DELETE 0' if no rows were affected
            if result.endswith("0"): raise MessageNotFoundException(id = message_id)
