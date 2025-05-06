import asyncio
import logging
import aiomysql
import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pydantic import AnyUrl
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Resource, Tool, TextContent

# Configure logging
logging.basicConfig(
    filename='mcp-server-mysql-pool.log',
    encoding='utf-8',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp-server-mysql-pool")

def get_db_config() -> dict:
    """Get database configuration from environment variables."""
    db_config = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "db": os.getenv("MYSQL_DB"),
        "pool_size": int(os.getenv("MYSQL_POOL_SIZE", 10)),
    }
    if not all([db_config["user"], db_config["password"], db_config["db"]]):
        raise ValueError("Missing required database configuration")
    return db_config

@asynccontextmanager
async def server_lifespan(server: Server) -> AsyncIterator[dict]:
    """Manage server startup and shutdown lifecycle."""
    db_config = get_db_config()
    pool = await aiomysql.create_pool(
        host=db_config["host"],
        port=db_config["port"],
        user=db_config["user"],
        password=db_config["password"],
        db=db_config["db"],
        minsize=1,  # Minimum number of connections
        maxsize=db_config["pool_size"],  # Maximum number of connections in the pool
    )
    try:
        yield {"db_pool": pool}
    finally:
        # Clean up on shutdown
        pool.close()
        await pool.wait_closed()
        logger.info("Connection pool closed.")


# Pass lifespan to server
server = Server("mcp-server-mysql-pool", lifespan=server_lifespan)

SCHEMA_PATH = 'schema'

@server.list_resources()
async def list_resources() -> list[Resource]:
    """List MySQL tables as resources."""
    ctx = server.request_context
    logger.info("Listing resources...")
    db_pool = ctx.lifespan_context["db_pool"]
    logger.info(f"DB: {db_pool}")
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("SHOW TABLES")
                tables = await cursor.fetchall()
                logger.info(f"Tables: {tables}")
                resources = []
                for table in tables:
                    resources.append(
                        Resource(
                            uri=f"mysql://{table[0]}/{SCHEMA_PATH}",
                            name=f"Table: {table[0]}",
                            mimeType="application/json",
                            description=f"Table schema, create statement and sample data: {table[0]}"
                        )
                    )
                return resources
    except Exception as e:
        logger.error(f"Error: {e}")
        raise RuntimeError(f"Failed to list resources: {e}")

@server.read_resource()
async def read_resource(uri: AnyUrl) -> str:
    ctx = server.request_context
    db_pool = ctx.lifespan_context["db_pool"]

    uri_str = str(uri)
    if not uri_str.startswith("mysql://"):
        raise ValueError(f"Invalid URI: {uri_str}")
    path_components = uri_str[8:].split("/")
    if len(path_components) != 2:
        raise ValueError(f"Invalid URI: {uri_str}")
    table_name = path_components[0]
    schema_path = path_components[1]
    if schema_path != SCHEMA_PATH:
        raise ValueError(f"Invalid schema path: {schema_path}")
    logger.info(f"Reading resource: {uri_str}")
    try:
        async with db_pool.acquire() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(f"DESCRIBE {table_name}")
                columns = await cursor.fetchall()

                await cursor.execute(f"SHOW CREATE TABLE {table_name}")
                create_statement = (await cursor.fetchone())[1]

                await cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
                sample_data = await cursor.fetchall()

                schema = f"## Table: {table_name}\n\n"
                schema += "### Columns:\n\n"
                schema += "| Field | Type | Null | Key | Default | Extra |\n"
                schema += "|-------|------|------|-----|---------|-------|\n"
                
                for column in columns:
                    field, type_, null, key, default, extra = column
                    schema += f"| {field} | {type_} | {null} | {key} | {default or 'NULL'} | {extra} |\n"
                
                schema += f"\n### Create Table SQL:\n\n```sql\n{create_statement}\n```\n"

                schema += f"\n### Sample Data:\n\n"
                schema += "| " + " | ".join([col[0] for col in columns]) + " |\n"
                schema += "| " + " | ".join(["---" for _ in columns]) + " |\n"
                for row in sample_data:
                    schema += "| " + " | ".join([str(value) for value in row]) + " |\n"

                return schema
    except Exception as e:
        logger.error(f"Error: {e}")
        return f"Error: {e}"
    
@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    logger.info("Listing tools...")
    return [
        Tool(
            name="query",
            description="Run a read-only SQL query",
            inputSchema={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL query to execute"
                    }
                },
                "required": ["sql"]
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Call a tool with the given name and arguments."""
    ctx = server.request_context
    db_pool = ctx.lifespan_context["db_pool"]

    if name == "query":
        sql = arguments.get("sql")
        if not sql:
            raise ValueError("SQL query is required.")
        if not sql.lower().startswith("select") and not sql.lower().startswith("show") and not sql.lower().startswith("describe"):
            raise ValueError("Only SELECT queries are allowed.")
        logger.info(f"Executing SQL query: {sql}")
        try:
            async with db_pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(sql)
                    result = await cursor.fetchall()
                    logger.info(f"Query result: {result}")
                    columns = [desc[0] for desc in cursor.description]
                    logger.info(f"Cursor description: {cursor.description}")
                    # Format as markdown table
                    output = "| " + " | ".join(columns) + " |\n"
                    output += "| " + " | ".join(["---"] * len(columns)) + " |\n"
                    for row in result:
                        output += "| " + " | ".join([str(value) for value in row]) + " |\n"
                    return [
                        TextContent(
                            type="text",
                            text=output
                        )
                    ]
        except Exception as e:
            logger.error(f"Error: {e}")
            return [TextContent(content=str(e), mimeType="text/plain")]
    else:
        raise ValueError(f"Tool '{name}' not found.")

async def main():
    """Main entry point to run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        try:
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
        except Exception as e:
            raise RuntimeError(f"Failed to run server: {e}")

if __name__ == "__main__":
    asyncio.run(main())
