# Typing
from typing import Dict, Any, Optional
# Exception
from app.exceptions.threads import ThreadNotFoundException
# Shared helpers
from app.db.postgres.existence import check_row_exists
# Other components
import asyncpg, json

class PostgresThreadStore:
    @staticmethod
    async def insert_thread(pool: asyncpg.Pool,
                            thread_id: str,
                            metadata: Optional[Dict[str, Any]] = None,
                            tool_resources: Optional[Dict[str, Any]] = None) -> None:
        """
        Insert a new thread into the database.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: Unique identifier for the thread
            metadata: Optional metadata dictionary for the thread
            tool_resources: Optional tool resources dictionary for the thread
        """
        query = """
        INSERT INTO threads (id, metadata, tool_resources, created_at)
        VALUES ($1, $2::jsonb, $3::jsonb, now())
        ON CONFLICT (id) DO NOTHING
        """
        async with pool.acquire() as conn:
            await conn.execute(query, thread_id, json.dumps(metadata or {}), json.dumps(tool_resources or {}))

    @staticmethod
    async def get_thread(pool: asyncpg.Pool,
                         thread_id: str):
        """
        Retrieve a thread by its ID.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: Unique identifier for the thread
            
        Returns:
            Dictionary containing thread data with parsed JSON fields
            
        Raises:
            ThreadNotFoundException: If thread with given ID doesn't exist
        """
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, metadata, tool_resources, created_at FROM threads WHERE id = $1", thread_id)
        if row is None:
            raise ThreadNotFoundException(thread_id = thread_id)
        result = dict(row)
        # Parse JSON strings back to dictionaries
        result["metadata"] = json.loads(result.get("metadata", "{}"))
        result["tool_resources"] = json.loads(result.get("tool_resources", "{}"))
        return result

    @staticmethod
    async def is_thread_exists(pool: asyncpg.Pool,
                                 thread_id: str):
        """
        Check if a thread exists in the database.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: Unique identifier for the thread
            
        Raises:
            ThreadNotFoundException: If thread with given ID doesn't exist
        """
        async with pool.acquire() as conn:
            # Ensure thread exists
            if not await check_row_exists(conn, "threads", "id", thread_id):
                raise ThreadNotFoundException(thread_id=thread_id)

    @staticmethod
    async def delete_thread(pool: asyncpg.Pool,
                            thread_id: str) -> bool:
        """
        Delete a thread by its ID.
        
        Args:
            pool: PostgreSQL connection pool
            thread_id: Unique identifier for the thread
            
        Returns:
            bool: True if thread was deleted, False otherwise
            
        Raises:
            ThreadNotFoundException: If thread with given ID doesn't exist
        """
        async with pool.acquire() as conn:
            result = await conn.execute("DELETE FROM threads WHERE id=$1", thread_id)
        if result.endswith("0"):
            raise ThreadNotFoundException(thread_id=thread_id)
        return True
