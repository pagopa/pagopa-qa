---
name: mermaid-flow
description: Generate a Mermaid workflow diagram (Markdown-first, optional SVG) from a source Markdown asset.
applyTo: docs/flows/**
---

# Skill: Mermaid Flow Generator

> This is a **distributed asset**. The catalog delivers this content (ephemeral
> load or hard install); your **local model** applies it. The catalog runs nothing.

## When to use

Use when the user asks to generate or refresh a Mermaid workflow diagram from a
source Markdown file (agent, prompt, instruction, or document).

## Inputs

- `source_markdown` (string, required): raw Markdown of the source asset.
- `orientation` (string, optional, default `TD`, one of `TD` | `LR`).
- `max_nodes` (integer, optional, default `15`): split the diagram if it would
  exceed this node count.

## Procedure (for the local model)

1. Extract the meaningful steps/headings from `source_markdown`.
2. Emit a fenced ```mermaid `flowchart <orientation>` block, one node per step,
   linking consecutive steps with `-->`.
3. Keep at most `max_nodes` nodes; if more are needed, produce multiple diagrams.
4. Suggest an output basename derived from the first heading (kebab-case).

## Output contract

- A fenced Mermaid diagram block.
- A suggested file basename.
