---
name: cloudflare-bindings
description: >-
  Interact with Cloudflare Workers, D1 databases, KV namespaces, R2 buckets,
  and Hyperdrive bindings via the Cloudflare Bindings MCP server
  (https://bindings.mcp.cloudflare.com/mcp) and Wrangler CLI. Activate this
  skill when inspecting, querying, migrating, or managing Cloudflare
  resources, Workers, or D1 databases.
---

# Cloudflare Workers Bindings (MCP & Wrangler)

Use this skill whenever a task involves inspecting, querying, configuring, or managing Cloudflare Workers and their storage/compute bindings (D1, KV, R2, Hyperdrive).

## 1. MCP Server Configuration

* **Server Name**: `cloudflare-bindings`
* **Streamable HTTP Endpoint**: `https://bindings.mcp.cloudflare.com/mcp`

### Configuration Reference

* **Antigravity (`mcp_config.json`)**:
  ```json
  {
    "mcpServers": {
      "cloudflare-bindings": {
        "url": "https://bindings.mcp.cloudflare.com/mcp"
      }
    }
  }
  ```
* **Kilo / OpenCode (`.kilo/kilo.jsonc`)**:
  ```json
  {
    "mcp": {
      "cloudflare-bindings": {
        "type": "remote",
        "url": "https://bindings.mcp.cloudflare.com/mcp",
        "enabled": true
      }
    }
  }
  ```

---

## 2. Core MCP Capabilities

When the `cloudflare-bindings` MCP server is connected, prefer its native tools over raw CLI calls for remote cloud state inspection:

1. **Account Context**
   * `accounts_list`: List available Cloudflare accounts.
   * `set_active_account`: Set the active `account_id` required by subsequent binding tools.
2. **D1 Serverless SQL Databases**
   * `d1_databases_list`: List all D1 databases in the account.
   * `d1_database_get`: Inspect metadata and size of a specific D1 database.
   * `d1_database_query`: Execute parameterized SQL queries (`SELECT`, `INSERT`, `UPDATE`, schema inspection) against a D1 database.
   * `d1_database_create` / `d1_database_delete`: Provision or remove D1 databases.
3. **Workers**
   * `workers_list`: List deployed Cloudflare Workers.
   * `workers_get_worker`: Inspect Worker metadata, bindings, and settings.
   * `workers_get_worker_code`: Retrieve deployed Worker script code and modules.
4. **KV Namespaces**
   * `kv_namespaces_list`, `kv_namespace_get`, `kv_namespace_create`, `kv_namespace_update`, `kv_namespace_delete`.
5. **R2 Object Storage Buckets**
   * `r2_buckets_list`, `r2_bucket_get`, `r2_bucket_create`, `r2_bucket_delete`.
6. **Hyperdrive**
   * `hyperdrive_list_configs`, `hyperdrive_get_config`, `hyperdrive_create_config`, `hyperdrive_edit_config`, `hyperdrive_delete_config`.

---

## 3. Standard Agent Workflow

1. **Initialize Account Context**:
   * Call `accounts_list` first if the active Cloudflare account is not set, then call `set_active_account`.
2. **Sync with `wrangler.jsonc`**:
   * Always check `wrangler.jsonc` at the repository root to verify the project's binding names (`DB`, `ASSETS`, etc.) and `database_id` values before querying or modifying bindings.
   * In this workspace (`ac-luxury-aesthetics`):
     * Worker name: `ac-luxury-aesthetics`
     * D1 Binding: `DB` → `ac-luxury-db` (`04d25f7f-7dea-46af-b0ec-4512392b8042`)
     * Migrations directory: `migrations/`
3. **Database Safety**:
   * Default to read-only `SELECT` or `PRAGMA` queries when diagnosing issues.
   * Never run destructive commands (`DROP`, `TRUNCATE`, unguarded `DELETE`) on remote D1 databases without explicit user confirmation.
   * Keep schema changes tracked as numbered SQL files inside `migrations/` rather than ad-hoc remote mutations.
4. **Local Development Fallback (`wrangler`)**:
   * The remote MCP server inspects **Cloudflare remote resources**. For local development state (`.wrangler/state`), use Wrangler CLI:
     ```bash
     npx wrangler d1 execute ac-luxury-db --local --command "SELECT * FROM appointments LIMIT 10;"
     ```
