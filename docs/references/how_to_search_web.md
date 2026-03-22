# Technical Analysis of Web Search Functionality in OpenCode

---

## Introduction

OpenCode is a rapidly evolving open-source coding agent designed to augment software development workflows with AI-powered assistance, including real-time web search and retrieval capabilities. As the landscape of AI coding assistants matures, the ability to access up-to-date information from the internet—beyond the static knowledge of large language models (LLMs)—has become a critical differentiator. This report provides a comprehensive technical analysis of how OpenCode implements web search, examining its internal architecture, tool invocation flow, integration with external protocols like MCP (Model Context Protocol), and the ecosystem of plugins and configuration options that enable or extend web search functionality.

The analysis draws from official documentation, source code references, plugin repositories, community tutorials, and technical discussions. It covers the built-in `websearch` and `webfetch` tools, provider-based search via model SDKs, MCP server integration (notably with Exa AI), and the role of plugins such as `opencode-websearch` and `opencode-websearch-cited`. The report also details configuration strategies, permission models, and security considerations, providing actionable insights for users, administrators, and plugin developers seeking to enable, customize, or extend web search in OpenCode.

---

## 1. Overview of Web Search in OpenCode

OpenCode's web search capability is architected around the principle of **tool-based extensibility**. Rather than hardcoding search logic into the core, OpenCode exposes a set of tools—invokable by LLMs or users—that perform specific actions such as searching the web, fetching web content, or integrating with external APIs. This modular approach allows for both built-in and plugin-based extensions, as well as seamless integration with external protocols like MCP.

### 1.1. Key Web-Related Tools

OpenCode distinguishes between two primary web tools:

- **websearch**: Performs internet-wide search queries, returning a list of relevant results (titles, snippets, URLs). Analogous to using a search engine.
- **webfetch**: Retrieves and processes the content of a specific web page given its URL. Analogous to opening and reading a page in a browser.

This separation of concerns enables flexible workflows, such as searching for the latest documentation and then fetching and summarizing a specific result, all orchestrated by the LLM agent.

### 1.2. Tool Invocation Flow

When a user or LLM issues a prompt requiring external information, OpenCode's agent determines which tool(s) to invoke based on the task:

1. **Discovery**: If the prompt requires finding information (e.g., "What are the new features in React 19?"), the agent calls `websearch`.
2. **Retrieval**: If the prompt specifies a URL or requests reading a particular page, the agent calls `webfetch`.
3. **Chained Operations**: For complex queries, the agent may chain both tools—searching first, then fetching and summarizing a selected result.

This tool invocation is governed by OpenCode's permissions and configuration system, ensuring that only authorized tools are executed and that user preferences are respected.

---

## 2. Architecture and Internal Implementation

### 2.1. Core Implementation Files

The core logic for web search in OpenCode resides in the following source files:

- `packages/opencode/src/tool/websearch.ts`: Implements the `websearch` tool, handling query construction, remote invocation, and result parsing.
- `packages/opencode/src/tool/webfetch.ts`: Implements the `webfetch` tool, handling HTTP retrieval, content conversion (e.g., HTML to Markdown), and output formatting.
- `packages/opencode/src/tool/registry.ts`: Manages tool registration and enablement logic, including provider checks and feature flags.
- `packages/opencode/src/flag/flag.ts`: Defines feature flags and environment variable triggers for tool availability.

These files collectively define the behavior, parameters, and enablement conditions for web search and fetch operations.

### 2.2. Web Search Tool (`websearch`)

The `websearch` tool is designed for **broad internet discovery**. Its core workflow is as follows:

- **Invocation**: When triggered, it constructs a JSON-RPC request targeting Exa AI's hosted MCP endpoint (`https://mcp.exa.ai/mcp`).
- **Method**: The request uses the `tools/call` method, specifying the tool name `web_search_exa`.
- **Parameters**: Supports parameters such as `query` (search keywords), `numResults` (number of results), `livecrawl` (real-time crawling preference), and `type` (search depth: auto, fast, deep).
- **Response Handling**: Processes the response as a Server-Sent Events (SSE) stream, extracting search results in Markdown format.
- **Timeouts and Error Handling**: Enforces a 25-second timeout and provides descriptive errors if the search fails or returns no results.

This design leverages Exa AI's MCP service as a backend, offloading the complexity of web crawling, ranking, and snippet generation.

### 2.3. Web Fetch Tool (`webfetch`)

The `webfetch` tool is optimized for **retrieving and processing specific web pages**:

- **Invocation**: Accepts a `url` parameter and optional output formatting options (`markdown`, `text`, `html`).
- **Retrieval**: Fetches the raw HTML or text content of the specified URL.
- **Content Processing**: Converts HTML to Markdown using the Turndown library, or extracts plain text as needed.
- **Limits**: Enforces a maximum response size (5MB) and a configurable timeout (default 30 seconds, max 120 seconds).
- **Error Handling**: Handles common issues such as oversized responses or blocked requests (e.g., Cloudflare protection).

Unlike `websearch`, `webfetch` does not perform discovery; it is strictly for retrieval and summarization of known URLs.

### 2.4. Codesearch Tool

OpenCode also includes a `codesearch` tool, which is similar in architecture to `websearch` but optimized for technical documentation, code examples, and API usage patterns. It calls the `get_code_context_exa` tool on Exa's MCP endpoint, returning high-token-count context relevant to programming queries.

---

## 3. Integration with Exa AI and MCP (Model Context Protocol)

### 3.1. Exa AI Hosted MCP Service

A cornerstone of OpenCode's web search capability is its integration with **Exa AI's hosted MCP service**. MCP (Model Context Protocol) is an open protocol for connecting AI agents to external tools and data sources in a standardized, secure manner.

#### 3.1.1. MCP Endpoint and Protocol

- **Endpoint**: `https://mcp.exa.ai/mcp`
- **Protocol**: JSON-RPC 2.0 over HTTP, supporting both synchronous and streaming (SSE) responses.
- **Authentication**: No API key required for public Exa MCP usage in OpenCode; the tool connects directly without authentication.
- **Tools Exposed**: `web_search_exa`, `get_code_context_exa`, and others for research papers, company info, tweets, etc.

This architecture allows OpenCode to delegate search and retrieval tasks to Exa's infrastructure, benefiting from its up-to-date index and advanced ranking algorithms.

#### 3.1.2. Enablement Logic

The availability of `websearch` and `codesearch` tools is controlled by the following conditions:

- **Provider Check**: Enabled if the active model provider is `opencode` (i.e., OpenCode Zen hosted models).
- **Environment Variables**: Enabled if `OPENCODE_ENABLE_EXA` is set to `true` or `1`, or if experimental flags like `OPENCODE_EXPERIMENTAL` are active.
- **Configuration**: Can be enabled or disabled via `opencode.json` permissions and tool settings.

This ensures that web search is only available when the backend infrastructure is accessible and authorized.

#### 3.1.3. Parameters and Output

The `websearch` tool supports several parameters, including:

| Parameter             | Description                                 | Default / Notes                |
|-----------------------|---------------------------------------------|-------------------------------|
| `query`               | Search keywords                             | Required                      |
| `numResults`          | Number of results to return                 | 8 (Exa API default)           |
| `type`                | Search depth (`auto`, `fast`, `deep`)       | `auto`                        |
| `livecrawl`           | Real-time crawl preference                  | `fallback`                    |
| `contextMaxCharacters`| Maximum context characters                  | 10,000                        |

The output is typically a Markdown-formatted list of results, each with a title, snippet, and URL. The agent can then use `webfetch` to retrieve and summarize a selected result.

---

## 4. Provider-Based Web Search and Model SDKs

### 4.1. Provider Abstraction

OpenCode is **provider-agnostic** by design, supporting 75+ LLM providers and local models via a unified configuration interface. Providers are defined in the `provider` section of `opencode.json`, with each provider specifying available models, API endpoints, and options.

### 4.2. Web Search via Model SDKs and Responses API

Some LLM providers (e.g., Anthropic, OpenAI) expose web search capabilities via their own APIs or SDKs. OpenCode can leverage these by:

- **Direct Tool Calls**: If the active model supports tool calling (e.g., OpenAI's `Responses API`), OpenCode can invoke web search tools natively.
- **Plugin Mediation**: Plugins such as `opencode-websearch` abstract provider-specific search mechanisms, allowing seamless integration regardless of the underlying provider.

This flexibility enables OpenCode to offer web search even when not using Exa MCP, provided the provider's API supports it.

### 4.3. Model Tagging and Selection

To control which model handles web search, OpenCode supports **model tagging** in the configuration:

- `"websearch": "auto"`: Use this model as a fallback for web search when the active model is unsupported.
- `"websearch": "always"`: Always use this model for web search, regardless of the active chat model.

This allows fine-grained control over model selection for search tasks, optimizing for cost, latency, or provider capabilities.

---

## 5. Plugins for Web Search: Extending and Customizing Functionality

OpenCode's plugin system enables the community to extend web search capabilities beyond the built-in tools. Two notable plugins are `opencode-websearch` and `opencode-websearch-cited`.

### 5.1. opencode-websearch Plugin (emilsvennesson)

This plugin provides a **provider-agnostic web search tool** inspired by Claude Code's WebSearch:

- **Supported Providers**: Anthropic (`@ai-sdk/anthropic`), OpenAI (`@ai-sdk/openai`), and others via the Responses API.
- **Installation**: Add `"plugin": ["opencode-websearch"]` to `opencode.json`; OpenCode installs it automatically at startup.
- **Model Selection**: Honors model tagging (`auto` or `always`) for web search delegation.
- **Development Workflow**: Supports local development via symlinking the plugin source into the OpenCode plugin directory. Edits take effect on restart.
- **Commands**: Provides standard Bun/NPM scripts for formatting, linting, type checking, and building.

The plugin architecture allows for rapid iteration and customization, making it suitable for advanced users and organizations with specific requirements.

### 5.2. opencode-websearch-cited Plugin (ghoulr)

This plugin focuses on **LLM-grounded web search with inline citations**:

- **Tool Exposed**: `websearch_cited`, which returns answers with inline citations and a "Sources" list.
- **Backends**: Supports Google, OpenAI, and OpenRouter as search providers.
- **Installation**: Add `"opencode-websearch-cited@<version>"` to the plugin list in `opencode.json`, ensuring it is last to avoid auth conflicts.
- **Configuration**: Requires specifying a `websearch_cited` model in the provider options.
- **Output Format**: Returns answers with numbered citations (e.g., `[1]`) and a corresponding sources list, improving factuality and verifiability.
- **Development**: Supports local testing via file URLs and Bun scripts.

This plugin is particularly valuable for scenarios where **traceability and source attribution** are critical, such as technical research or academic writing.

### 5.3. Plugin Development and Local Testing

OpenCode supports local plugin development via symlinking or direct placement in the plugin directory (`~/.config/opencode/plugins/` or `.opencode/plugins/`). Plugins can declare dependencies in a local `package.json`, which are installed via Bun at startup. This enables rapid prototyping and testing of custom tools, hooks, and integrations.

---

## 6. Configuration: Enabling and Customizing Web Search

### 6.1. Configuration File Locations and Precedence

OpenCode supports hierarchical configuration via `opencode.json` files at multiple levels:

- **Remote Config**: Organizational defaults from `.well-known/opencode`.
- **Global Config**: User-wide settings at `~/.config/opencode/opencode.json`.
- **Custom Config**: Overrides via the `OPENCODE_CONFIG` environment variable.
- **Project Config**: Project-specific settings in the project root.
- **.opencode Directories**: For agents, commands, plugins, etc.
- **Inline Config**: Runtime overrides via `OPENCODE_CONFIG_CONTENT`.

Settings are **merged**, with later sources overriding earlier ones for conflicting keys. This allows for flexible, layered customization.

### 6.2. Enabling Web Search

Web search can be enabled via several mechanisms:

- **Provider Selection**: Using OpenCode Zen hosted models enables web search by default.
- **Environment Variable**: Set `OPENCODE_ENABLE_EXA=true` (or `OPENCODE_EXPERIMENTAL=true`) to enable web search for other providers.
- **Permissions**: Ensure `"websearch": "allow"` is set in the `permission` section of `opencode.json`.
- **Plugin Installation**: Add web search plugins to the `plugin` array in `opencode.json`.

Example configuration to enable websearch:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "websearch": "allow"
  },
  "plugin": ["opencode-websearch"]
}
```

For plugin-based search, additional provider and model configuration may be required, as detailed in the plugin documentation.

### 6.3. Tool Permissions and Security

OpenCode's permission system allows fine-grained control over tool execution:

- **Allow**: Tool can be executed without user approval.
- **Ask**: User is prompted for approval before execution.
- **Deny**: Tool is disabled.

Permissions can be set globally or per agent, and wildcards are supported for batch configuration. For example, to require approval for all MCP tools:

```json
{
  "permission": {
    "mymcp_*": "ask"
  }
}
```

This ensures that sensitive operations, such as web search or external API calls, are subject to appropriate oversight.

### 6.4. MCP Server Configuration

To integrate external MCP servers (e.g., custom search backends), add entries under the `mcp` key in `opencode.json`:

- **Local MCP Server**:

```json
{
  "mcp": {
    "my-local-mcp-server": {
      "type": "local",
      "command": ["npx", "-y", "my-mcp-command"],
      "enabled": true,
      "environment": {
        "MY_ENV_VAR": "my_env_var_value"
      }
    }
  }
}
```

- **Remote MCP Server**:

```json
{
  "mcp": {
    "my-remote-mcp": {
      "type": "remote",
      "url": "https://my-mcp-server.com",
      "enabled": true,
      "headers": {
        "Authorization": "Bearer MY_API_KEY"
      }
    }
  }
}
```

MCP servers can be enabled or disabled per agent or globally, and support OAuth or API key authentication as needed.

---

## 7. Runtime Environment and CLI Usage

### 7.1. Environment Variables

Several environment variables influence web search behavior:

- `OPENCODE_ENABLE_EXA`: Enables Exa MCP-based web search.
- `OPENCODE_EXPERIMENTAL`: Enables experimental features, including web search.
- `OPENCODE_CONFIG`: Specifies a custom config file path.
- Provider-specific variables (e.g., `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) for authentication.

These can be set in shell profiles or passed at runtime to control feature availability.

### 7.2. CLI Usage Examples

To run OpenCode with web search enabled:

```bash
export OPENCODE_ENABLE_EXA=true
opencode
```

To specify a project-specific config:

```bash
opencode --config ./opencode.json
```

To select an agent with web search permissions:

```bash
opencode -a explore
```

Agents can be defined in `opencode.json` with specific tool permissions, enabling workflows such as "explore" (web research), "build" (local code editing), or "oracle" (read-only analysis).

---

## 8. Citations, Inline Sources, and Output Formatting

### 8.1. Inline Citations

Plugins like `opencode-websearch-cited` enhance the factuality and transparency of LLM outputs by embedding **inline citations**:

- Answers include numbered references (e.g., `[1]`) corresponding to a "Sources" list.
- Each source entry includes a title and URL.
- This approach aligns with best practices for LLM-grounded generation, improving trust and verifiability.

### 8.2. Output Formatting

Both `websearch` and `webfetch` support output formatting options:

- **Markdown**: Default for documentation, blogs, and READMEs.
- **Text**: Plain text output.
- **HTML**: Raw HTML for structural analysis.

The agent selects the appropriate format based on the prompt or tool parameters. For most use cases, Markdown is sufficient and provides a clean, readable summary.

---

## 9. Security, Permissions, and Tool Approval

### 9.1. Security Considerations

Web search and fetch operations inherently involve external network requests and the processing of untrusted content. OpenCode mitigates risks via:

- **Permission Checks**: Tools require explicit permission to execute, with options for user approval or denial.
- **Environment Isolation**: Plugins and tools run in controlled environments, and sensitive operations (e.g., reading `.env` files) can be restricted via plugin hooks.
- **Authentication**: Provider credentials are stored securely, and MCP servers support OAuth or API key authentication as appropriate.

Administrators are encouraged to review and restrict tool permissions, especially in shared or multi-user environments.

### 9.2. Tool Approval Workflow

When a tool is set to `"ask"` in the permissions, OpenCode prompts the user for approval before execution. This is particularly useful for:

- **Sensitive Operations**: Shell commands, file edits, or external API calls.
- **MCP Tools**: Batch approval or denial of all tools from a given MCP server via wildcards.

This workflow balances flexibility with security, ensuring that users retain control over potentially impactful actions.

---

## 10. Summary Table: Key Components and Configuration Options

| Component / Option                | Purpose / Description                                                                 | Location / Example                                                                 |
|-----------------------------------|--------------------------------------------------------------------------------------|------------------------------------------------------------------------------------|
| `websearch` tool                  | Performs internet-wide search via Exa MCP                                            | `src/tool/websearch.ts`, enabled via provider or `OPENCODE_ENABLE_EXA`             |
| `webfetch` tool                   | Fetches and processes content from a specific URL                                    | `src/tool/webfetch.ts`, enabled by default                                         |
| Exa MCP integration               | Backend for websearch/codesearch, JSON-RPC over HTTP                                 | Endpoint: `https://mcp.exa.ai/mcp`                                                 |
| Provider-based search             | Uses model SDKs or Responses API for web search                                      | Provider config in `opencode.json`                                                 |
| `opencode-websearch` plugin       | Provider-agnostic web search plugin                                                  | `"plugin": ["opencode-websearch"]` in `opencode.json`                              |
| `opencode-websearch-cited` plugin | Web search with inline citations and sources list                                    | `"plugin": ["opencode-websearch-cited@<version>"]` in `opencode.json`              |
| Permissions                       | Control tool execution (`allow`, `ask`, `deny`)                                      | `"permission": { "websearch": "allow" }` in `opencode.json`                        |
| MCP server config                 | Add local or remote MCP servers for custom tools                                     | `"mcp": { ... }` in `opencode.json`                                                |
| Model tagging                     | Select model for web search (`auto`, `always`)                                       | `"websearch": "auto"` in provider/model options                                    |
| Environment variables             | Enable features and set credentials                                                  | `OPENCODE_ENABLE_EXA`, `OPENCODE_CONFIG`, provider API keys                        |
| Plugin development                | Extend functionality, add custom tools                                               | Place in `.opencode/plugins/` or `~/.config/opencode/plugins/`                     |
| Output formatting                 | Control result format (`markdown`, `text`, `html`)                                   | Tool parameters or agent prompt                                                    |
| CLI usage                         | Run with specific config, agent, or environment                                      | `opencode --config ./opencode.json -a explore`                                     |

This table summarizes the main components, configuration options, and their typical locations or usage patterns within the OpenCode ecosystem.

---

## 11. Advanced Topics and Development Workflows

### 11.1. Plugin Development and Local Testing

Developers can create and test plugins locally by:

1. Cloning the plugin repository.
2. Installing dependencies (`bun install` or `npm install`).
3. Symlinking the plugin entry point into the OpenCode plugin directory.
4. Restarting OpenCode to load the plugin from source.

This workflow enables rapid iteration and debugging, with changes taking effect on the next startup. Plugins can also declare dependencies in a local `package.json`, which are installed automatically.

### 11.2. MCP Server Development

For advanced integration, developers can implement custom MCP servers (e.g., `opencode-mcp` by nosolosoft) to expose additional tools or workflows to OpenCode. These servers can be written in any language (e.g., Python), and are configured in `opencode.json` with the appropriate command, arguments, and environment variables. MCP servers can expose tools for executing OpenCode CLI commands, managing sessions, or integrating with external APIs.

---

## 12. Practical Examples

### 12.1. Enabling Web Search for Non-Zen Users

For users not on OpenCode Zen hosted models, enable web search by setting the environment variable:

```bash
export OPENCODE_ENABLE_EXA=true
```

Then restart OpenCode. The `websearch` tool will now be available for use by agents and plugins.

### 12.2. Agent Configuration for Web Research

Define an agent in `opencode.json` with web search permissions:

```json
{
  "agent": {
    "explore": {
      "description": "Web research agent",
      "model": "google/gemini-2.5-flash",
      "tools": {
        "webfetch": true,
        "websearch": true
      }
    }
  }
}
```

Invoke this agent via the CLI:

```bash
opencode -a explore
```

### 12.3. Plugin Installation Example

To install the `opencode-websearch-cited` plugin:

```json
{
  "plugin": [
    "...other plugins",
    "opencode-websearch-cited@1.2.0"
  ]
}
```

Specify the model for cited search in the provider options:

```json
{
  "provider": {
    "openai": {
      "options": {
        "websearch_cited": {
          "model": "gpt-5.2"
        }
      }
    }
  }
}
```

---

## 13. Limitations and Troubleshooting

### 13.1. Common Pitfalls

- **Websearch Unavailable**: Ensure the correct provider is active or `OPENCODE_ENABLE_EXA` is set.
- **URL Format Errors**: `webfetch` requires URLs to start with `http://` or `https://`.
- **Page Size Limits**: `webfetch` enforces a 5MB maximum response size.
- **Blocked Requests**: Some sites block automated requests; OpenCode retries with a standard User-Agent but may still fail.
- **Poor Search Results**: Use specific, well-formed queries for best results.

### 13.2. Debugging

- **Check Environment Variables**: Use `echo $OPENCODE_ENABLE_EXA` to verify.
- **Review Permissions**: Ensure tool permissions are set to `allow` or `ask` as needed.
- **Plugin Conflicts**: Place citation plugins last in the plugin list to avoid authentication issues.

---

## 14. Conclusion

OpenCode's web search functionality exemplifies a modern, extensible approach to integrating real-time internet knowledge into AI coding workflows. By leveraging a combination of built-in tools, provider-based APIs, MCP server integration (notably with Exa AI), and a vibrant plugin ecosystem, OpenCode empowers users to access, retrieve, and cite the latest information from the web—bridging the gap between static LLM knowledge and the dynamic, ever-changing landscape of software development.

The architecture's modularity, robust configuration system, and security-conscious permission model make it suitable for a wide range of use cases, from individual developers seeking up-to-date documentation to organizations requiring traceable, citation-rich research outputs. As the ecosystem continues to evolve, further innovations in plugin development, MCP server integration, and output formatting are likely to enhance both the breadth and depth of OpenCode's web search capabilities.

---

**Key Takeaway:**  
OpenCode performs web search primarily via its `websearch` tool, which connects to Exa AI's hosted MCP service using JSON-RPC over HTTP. This is enabled by default for Zen hosted models or via the `OPENCODE_ENABLE_EXA` environment variable. Additional flexibility is provided by provider-based search via model SDKs and a rich ecosystem of plugins, notably `opencode-websearch` and `opencode-websearch-cited`. Configuration is managed through layered `opencode.json` files, with fine-grained permissions and security controls. The architecture supports both built-in and custom MCP servers, enabling advanced workflows and integrations. Plugin development is straightforward, supporting local testing and rapid iteration. Output formatting and citation features further enhance the utility and trustworthiness of web search results in OpenCode.

---
了解しました。OpenCode がどのように WebSearch 機能を実装しているかを調査します。具体的には、内部ツール、外部 API、MCP（Model Context Protocol）などの利用有無、関連モジュールや構成ファイル、検索クエリの処理フローなどを調べます。

🕵️‍♂️ この調査には数分かかりますので、その間は離席していただいても大丈夫です。レポートはこの会話に保存されます。
