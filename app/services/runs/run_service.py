# Typing
from typing import Optional, Literal
# Schema
from app.schemas.runs import RunObject, RunListObject
# Postgres DB
from app.db.postgres import PostgresRunStore
# Utils
from app.utils.messaging import normalize_run_usage
# Other components
import asyncpg


class RunService:
    @staticmethod
    async def list_runs(postgres_pool: asyncpg.Pool,
                        thread_id: str,
                        limit: int,
                        after: Optional[str],
                        before: Optional[str],
                        order: Literal["asc", "desc"] = "desc") -> RunListObject:
        """List runs for a thread with keyset pagination."""
        run_objects = await PostgresRunStore.get_runs(pool = postgres_pool,
                                                      thread_id = thread_id,
                                                      limit = limit,
                                                      after = after,
                                                      before = before,
                                                      order = order)
        if len(run_objects) == 0:
            return RunListObject(data = [])

        for obj in run_objects:
            obj["usage"] = normalize_run_usage(obj.get("usage"))

        run_objects = [RunObject.model_validate(obj) for obj in run_objects]
        return RunListObject(data = run_objects,
                             first_id = run_objects[0].id,
                             last_id = run_objects[-1].id)

    @staticmethod
    async def retrieve_run(postgres_pool: asyncpg.Pool,
                           thread_id: str,
                           run_id: str) -> RunObject:
        """Retrieve a single run by ID."""
        run_object = await PostgresRunStore.get_run(pool = postgres_pool,
                                                    thread_id = thread_id,
                                                    run_id = run_id)
        run_object["usage"] = normalize_run_usage(run_object.get("usage"))
        return RunObject.model_validate(run_object)