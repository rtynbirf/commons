<!--
SPDX-FileCopyrightText: 2026 COMMONS contributors
SPDX-License-Identifier: Apache-2.0
-->

# Готовое тело PR (вставить в compare-URL: main...rtynbirf:n8n-docs:docs/mcp-trigger-parameters)

Заголовок PR:

    docs(mcp server trigger): document OAuth2 auth option and missing parameters

Тело PR (по шаблону n8n-docs):

---

## Summary

The MCP Server Trigger node gained parameters that the docs page does not mention yet. This PR brings the page in line with the node source ([McpTrigger.node.ts](https://github.com/n8n-io/n8n/blob/master/packages/%40n8n/nodes-langchain/nodes/mcp/McpTrigger/McpTrigger.node.ts), node versions 1 / 1.1 / 2 / 2.1):

- **Authentication** now lists the `n8n User Auth (OAuth2)` option (node version 2+), which exists in the node's options list between `None` and `Bearer Auth`.
- Documents the three parameters that appear with that option:
    - **Require Workflow Execute Permission** (v2+, default: enabled);
    - **Trusted Source Name or ID** (v2+);
    - **Include User in Output** (v2.1+, default: enabled).
- Adds a missing **Instructions** parameter section (available on all node versions): optional instructions sent to MCP clients when they connect, which clients typically add to the model's system prompt.

Wording follows the parameter descriptions in the node source. Affects only `docs/integrations/builtin/core-nodes/n8n-nodes-langchain.mcptrigger.md`.

## Related PRs, Linear tickets, issues, and forum posts

Docs-only update: there is no accompanying code change in the main repo — the node parameters documented here already exist in `McpTrigger.node.ts` (versions 2 and 2.1 are shipped in `version: [1, 1.1, 2, 2.1]`). No known Linear ticket or issue for this specific page gap.

## Preview

Once CI finishes, the GitBook preview comment should show the updated MCP Server Trigger page rendering correctly (new list item plus three bullet parameters under Authentication, new Instructions section between Path and Templates).

## Contribution checklist

- [x] This isn't an [unaccepted submission type](https://docs.n8n.io/contribute/contribution-guide-for-n8n-docs#what-not-to-submit) (promotional/commercial content, personal preference edits, or changes to a page with `generated: true` in its frontmatter).
- [x] Writing follows the [style guide](https://docs.n8n.io/contribute/contribution-guide-for-n8n-docs/style-guide-for-n8n-docs): present tense, second person, active voice; bold UI elements; parameter names as they appear in the node panel.
- [x] Page frontmatter is unchanged; no auto-generated page is touched.
