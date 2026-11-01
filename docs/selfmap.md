# Самоописание организма

<!-- AUTO-GENERATED: python3 scripts/selfmap.py — ручные правки запрещены, правь реестры -->

Сгенерировано из живых реестров: `organs/registry.yaml` + `synapse/mcp-manifest.yaml`.

```mermaid
flowchart LR
  subgraph genome["Геном"]
    spec_kit["spec-kit<br/>MIT · dependency"]
    skills["skills<br/>по-навыковые (ToU Anthropic) · reference"]
    skills:::outside
    superpowers["superpowers<br/>MIT · reference"]
    prompts_chat["prompts.chat<br/>NOASSERTION · reference"]
    prompts_chat:::outside
  end
  subgraph metabolism["Метаболизм"]
    ollama["ollama<br/>MIT · dependency<br/>MCP: chat, embeddings, generate, list_models"]
    ollama:::wired
    llama_cpp["llama.cpp<br/>MIT · dependency<br/>MCP: completion, embedding"]
    llama_cpp:::wired
    transformers["transformers<br/>Apache-2.0 · dependency"]
  end
  subgraph memory["Память"]
    graphify["graphify<br/>Apache-2.0 · dependency"]
  end
  subgraph senses["Сенсорика"]
    markitdown["markitdown<br/>MIT · dependency<br/>MCP: convert_to_markdown"]
    markitdown:::wired
    firecrawl["firecrawl<br/>AGPL-3.0 · external"]
    firecrawl:::outside
    system_prompts_and_models_of_ai_tools["system-prompts-and-models-of-ai-tools<br/>GPL-3.0 · reference"]
    system_prompts_and_models_of_ai_tools:::outside
  end
  subgraph effectors["Эффекторы"]
    openclaw["openclaw<br/>MIT · dependency<br/>MCP: abort, health, send_message, status"]
    openclaw:::wired
    browser_use["browser-use<br/>MIT · dependency<br/>MCP: click, extract, navigate, screenshot"]
    browser_use:::wired
    rea["rea<br/>MIT · adapter"]
    hermes_agent["hermes-agent<br/>MIT · reference"]
  end
  subgraph nerves_alt["Нервные альтернативы"]
    langchain["langchain<br/>MIT · dependency"]
    dify["dify<br/>Apache-2.0 с условиями · adapter"]
    dify:::outside
    langflow["langflow<br/>MIT · reference"]
    n8n["n8n<br/>fair-code (Sustainable Use) · external"]
    n8n:::outside
  end
  subgraph glands["Железы"]
    ComfyUI["ComfyUI<br/>GPL-3.0 · external"]
    ComfyUI:::outside
    stable_diffusion_webui["stable-diffusion-webui<br/>AGPL-3.0 · external"]
    stable_diffusion_webui:::outside
  end
  subgraph skin["Кожа"]
    react["react<br/>MIT · dependency"]
    ui["ui<br/>MIT · dependency"]
    next_js["next.js<br/>MIT · dependency"]
  end
  subgraph selfmap["Самоописание"]
    excalidraw["excalidraw<br/>MIT · dependency"]
  end
  subgraph remote["Удалённость"]
    scrcpy["scrcpy<br/>Apache-2.0 · adapter"]
    rustdesk["rustdesk<br/>AGPL-3.0 · external"]
    rustdesk:::outside
  end
  subgraph immune_knowledge["Иммунитет (знания)"]
    Awesome_Hacking["Awesome-Hacking<br/>CC0-1.0 · reference"]
  end
  subgraph substrate["Субстрат"]
    linux["linux<br/>GPL-2.0 · substrate"]
    linux:::outside
    kubernetes["kubernetes<br/>Apache-2.0 · substrate"]
    kubernetes:::outside
    node["node<br/>MIT · substrate"]
    node:::outside
    go["go<br/>BSD-3-Clause · substrate"]
    go:::outside
    rust["rust<br/>MIT OR Apache-2.0 · substrate"]
    rust:::outside
  end
  subgraph reproduction["Репродукция"]
    build_your_own_x["build-your-own-x<br/>NOASSERTION · education"]
    build_your_own_x:::outside
    system_design_primer["system-design-primer<br/>NOASSERTION · education"]
    system_design_primer:::outside
    computer_science["computer-science<br/>MIT-подобная · education"]
    computer_science:::outside
  end
  brainstem_core["Ствол мозга<br/>SPEC-0001"]:::own
  synapse_gw["Синапсы: MCP-шлюз<br/>SPEC-0002"]:::own
  blood_jr["Кровь: конверт+журнал<br/>SPEC-0003"]:::own
  synapse_gw --> brainstem_core
  brainstem_core --> blood_jr
  synapse_gw --> blood_jr


  classDef own fill:#1b6e5a,color:#fff,stroke:#0d3f34;
  classDef wired fill:#2f7bd6,color:#fff,stroke:#1a4a8a;
  classDef outside fill:#9aa4ad,color:#222,stroke:#6b757e,stroke-dasharray:4 2;
```

## Легенда

- **Зелёный** — собственный код ядра (спеки SPEC-0001..0003).
- **Синий** — органы, объявленные в манифесте синапсов (доступны телу).
- **Серый пунктир** — внешний узел, субстрат или обучение: в тело не входит.

Регенерация: `python3 scripts/selfmap.py`.
