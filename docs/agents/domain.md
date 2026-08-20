# Domain Docs

**Layout: single-context.** One `CONTEXT.md` at the root plus `docs/adr/`.

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, or
- **`CONTEXT-MAP.md`** at the repo root if it exists — it points at one `CONTEXT.md` per context. Read each one relevant to the topic.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo (most repos):

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-event-sourced-orders.md
│   └── 0002-postgres-for-write-model.md
└── src/
```

Multi-context repo (presence of `CONTEXT-MAP.md` at the root):

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← system-wide decisions
└── src/
    ├── ordering/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← context-specific decisions
    └── billing/
        ├── CONTEXT.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## An ADR that changes the spec says which section

`docs/spec/farmsync-solver-desktop-app.md` is written to be implementable without
the issue tracker. So an ADR that contradicts it splits the project in two: the
code follows the ADR, and anyone building from the spec builds the old behaviour.
That has already happened twice, in
[#56](https://github.com/errored-app/dibycap-solver-farmsync/issues/56) and
[#57](https://github.com/errored-app/dibycap-solver-farmsync/issues/57), both from
ADRs written after the spec was signed off.

Before an ADR is finished, grep the spec for what it decides. If a section now
says something the ADR contradicts, the ADR carries a **Reverses** line naming
those sections:

> **Reverses:** spec §5.1, §5.4, §5.5 and §9.7, which describe a paused service as
> terminal. Raised as #56.

That line is a claim that named sections of the spec are wrong until someone
fixes them, so **raising the fix is part of writing the ADR**, not a later tidy-up.
Fixing the spec in the same change is better still, when the ADR is small enough
that it can be.

Most ADRs reverse nothing and carry no line. Adding one where there is no conflict
is worse than useless — it teaches readers to skip it.

`CONTEXT.md` is not covered by this rule, because it does not need to be: an ADR
that renames or redefines a term updates the glossary in the same change. There is
no version of that drift a reader could detect.

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_
