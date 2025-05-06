# MCP Server MySQL Database Explorer

  

This MCP server connects to your MySQL database, providing seamless access to database schemas, tables, and query capabilities through LLMs.

  

## Features

  

- Connect to your MySQL database

- Expose table schemas, create statement and Sample data as resources

- Run read-only SQL queries with secure validation

  

## Setup Instructions

  

1. **Install Dependencies**

  
Project requires "uv" to be installed, here is "uv" installation instruction: https://docs.astral.sh/uv/getting-started/installation/#pypi

```bash

uv add "mcp[cli]" aiomysql

```

  

2. **Configure Environment Variables**

  

Create a `.env` file at the project root path with your database credentials:

  

```

MYSQL_HOST=localhost

MYSQL_PORT=3306

MYSQL_USER=root

MYSQL_PASSWORD=YOUR_PASSWORD

MYSQL_DB=YOUR_DB

MYSQL_POOL_SIZE=10

```

  

Or set these variables directly in your environment.

  

3. **Run in MCP interceptor

  

```bash

uv run mcp dev main.py

```

Navigate to http://127.0.0.1:6274/, then change the argument to this:
```
run --env-file=.env main.py
```

Click "Connect" to test the server


4. **Install the MCP Server in MCP Client (e.g. Cline, Cursor)

  Paste the JSON setting to your MCP Client:

```json

{
    "mcpServers": {
        "mcp-server-mysql-pool": {
            "command": "uv",
            "args": [
                "--directory",
                "YOUR/PROJECT/ROOT/PATH",
                "run",
                "main.py"
            ],
            "env": {
                "MYSQL_HOST": "localhost",
                "MYSQL_PORT": "3306",
                "MYSQL_USER": "YOUR_USER",
                "MYSQL_PASSWORD": "YOUR_PASSWORD",
                "MYSQL_DB": "YOUR_DB",
                "MYSQL_POOL_SIZE": "10"
            },
            "autoApprove": [
                "query"
            ]
        }
    }
}

```

  


  

