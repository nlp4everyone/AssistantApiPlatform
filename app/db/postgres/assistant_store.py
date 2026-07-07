# Typing
from typing import Dict, Any, Optional, Tuple, List, Set
# Schema
from app.schemas.assistants import CreateAssistantRequest
# Exception
from app.exceptions.assistants import AssistantNotFoundException
# Other components
import asyncpg, json

# Allowed table names to prevent SQL injection
ALLOWED_TABLES: Set[str] = {"assistants"}

class PostgresAssistantStore:
    @staticmethod
    def _validate_table_name(table_name: str) -> str:
        """Validate table name to prevent SQL injection."""
        if table_name not in ALLOWED_TABLES:
            raise ValueError(f"Invalid table name: {table_name}")
        return table_name
    
    @staticmethod
    def _validate_pagination_params(order: str, limit: int) -> Tuple[str, int]:
        """Validate pagination parameters."""
        order = order.lower()
        if order not in ("asc", "desc"):
            raise ValueError("Order must be 'asc' or 'desc'")
        if limit <= 0 or limit > 1000:
            raise ValueError("Limit must be between 1 and 1000")
        return order, limit

    @staticmethod
    async def create_assistant(pool :asyncpg.Pool,
                              assistant_id :str,
                              request: CreateAssistantRequest,
                              table_name :str = "assistants") -> int:
        """
        Create a new assistant record in the database.
        
        Args:
            pool: PostgreSQL connection pool
            assistant_id: Unique identifier for the assistant
            request: Assistant creation request with configuration
            table_name: Database table name (default: "assistants")
            
        Returns:
            int: Internal database ID of the created assistant
            
        Raises:
            ValueError: If assistant with ID already exists
            RuntimeError: If database insertion fails
        """
        validated_table = PostgresAssistantStore._validate_table_name(table_name)
        query = f"""
            INSERT INTO {validated_table} (
                assistant_id, model, description, instructions, metadata, name,
                reasoning_effort, response_format, temperature,
                tool_resources, tools, top_p
            ) VALUES (
                $1, $2, $3, $4, $5::jsonb,
                $6, $7, $8, $9,
                $10::jsonb, $11::jsonb, $12
            )
            RETURNING id
            """
        try:
            async with pool.acquire() as conn:
                return await conn.fetchval(
                    query,
                    assistant_id,  # external input
                    request.model,
                    request.description,
                    request.instructions,  # plain text, no ::jsonb
                    json.dumps(request.metadata) if request.metadata else None,
                    request.name,
                    request.reasoning_effort,
                    request.response_format,
                    request.temperature,
                    json.dumps(request.tool_resources.model_dump(exclude_none = True)) if request.tool_resources else None,
                    json.dumps([t.model_dump() for t in request.tools]) if request.tools else None,
                    request.top_p,
                )
        except asyncpg.UniqueViolationError:
            raise ValueError(f"Assistant with ID {assistant_id} already exists")
        except Exception as e:
            raise RuntimeError(f"Failed to insert assistant: {str(e)}")

    @staticmethod
    async def get_assistant(pool :asyncpg.Pool,
                           assistant_id: str,
                           table_name :str = "assistants") -> Dict[str, Any]:
        """
        Retrieve an assistant by its ID.
        
        Args:
            pool: PostgreSQL connection pool
            assistant_id: Unique identifier for the assistant
            table_name: Database table name (default: "assistants")
            
        Returns:
            Dict[str, Any]: Assistant record as dictionary
            
        Raises:
            AssistantNotFoundException: If assistant doesn't exist
        """
        validated_table = PostgresAssistantStore._validate_table_name(table_name)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT * FROM {validated_table} WHERE assistant_id = $1", assistant_id)
        if row is None:
            raise AssistantNotFoundException(id = assistant_id)
        return dict(row)

    @staticmethod
    async def count_assistants(pool :asyncpg.Pool,
                               table_name :str = "assistants") -> int:
        """
        Count total number of assistants in the database.
        
        Args:
            pool: PostgreSQL connection pool
            table_name: Database table name (default: "assistants")
            
        Returns:
            int: Total count of assistants
        """
        validated_table = PostgresAssistantStore._validate_table_name(table_name)
        async with pool.acquire() as conn:
            return await conn.fetchval(f'SELECT COUNT(*) FROM {validated_table};')

    @staticmethod
    async def list_assistants(pool: asyncpg.Pool,
                              order: str,
                              limit: int,
                              after: Optional[str] = None,
                              before: Optional[str] = None,
                              table_name :str = "assistants") -> List[asyncpg.Record]:
        """
        List assistants with keyset pagination.
        
        Args:
            pool: PostgreSQL connection pool
            order: Sort order ("asc" or "desc")
            limit: Maximum number of records to return
            after: Cursor for forward pagination (assistant_id)
            before: Cursor for backward pagination (assistant_id)
            table_name: Database table name (default: "assistants")
            
        Returns:
            List[asyncpg.Record]: List of assistant records
            
        Raises:
            ValueError: If pagination parameters are invalid
        """
        # Validate parameters
        validated_order, validated_limit = PostgresAssistantStore._validate_pagination_params(order, limit)
        validated_table = PostgresAssistantStore._validate_table_name(table_name)
        
        # Build the query
        query, params = _build_list_assistants_query(order = validated_order,
                                                     limit = validated_limit,
                                                     after = after,
                                                     before = before,
                                                     table_name = validated_table)
        # Make the query
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        # Response
        return rows

    @staticmethod
    async def delete_assistant(pool: asyncpg.Pool,
                               assistant_id :str,
                               table_name :str = "assistants") -> asyncpg.Record:
        """
        Delete an assistant by its ID.
        
        Args:
            pool: PostgreSQL connection pool
            assistant_id: Unique identifier for the assistant
            table_name: Database table name (default: "assistants")
            
        Returns:
            asyncpg.Record: The deleted assistant record
            
        Raises:
            AssistantNotFoundException: If assistant doesn't exist
        """
        validated_table = PostgresAssistantStore._validate_table_name(table_name)
        query = f"DELETE FROM {validated_table} WHERE assistant_id = $1 RETURNING *"
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, assistant_id)
        if row is None:
            raise AssistantNotFoundException(id = assistant_id)
        return row

def _build_list_assistants_query(order: str,
                                 limit: int,
                                 table_name: str,
                                 after: Optional[str] = None,
                                 before: Optional[str] = None) -> Tuple[str, List]:
    """
    Build a keyset pagination query for assistants table.

    Args:
        order: "asc" or "desc"
        limit: number of rows to fetch
        table_name: validated table name
        after: assistant_id for forward pagination
        before: assistant_id for backward pagination

    Returns:
        (query, params)
    """
    params: List = []

    # Base query
    sql = f"SELECT * FROM {table_name}\n"

    if after:
        comparator = ">" if order == "asc" else "<"
        sql += f"""
        WHERE created_at {comparator} (
            SELECT created_at FROM {table_name} WHERE assistant_id = $1
        )
        ORDER BY created_at {order.upper()} LIMIT $2
        """
        params = [after, limit]

    elif before:
        comparator = "<" if order == "asc" else ">"
        sql += f"""
        WHERE created_at {comparator} (
            SELECT created_at FROM {table_name} WHERE assistant_id = $1
        )
        ORDER BY created_at {order.upper()} LIMIT $2
        """
        params = [before, limit]

    else:
        sql += f"ORDER BY created_at {order.upper()} LIMIT $1"
        params = [limit]

    return sql.strip(), params