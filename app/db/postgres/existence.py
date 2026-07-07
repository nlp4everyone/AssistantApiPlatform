import asyncpg

async def check_row_exists(conn: asyncpg.Connection, table: str, id_column: str, id_value: str) -> bool:
    """Check whether a row exists in `table`, using an already-acquired connection."""
    return await conn.fetchval(f"SELECT 1 FROM {table} WHERE {id_column} = $1", id_value) is not None