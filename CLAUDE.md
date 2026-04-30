## Code Design Principles

Follow SOLID principles on all new code and refactors:

- **S** — Each class has one reason to change. Extraction agents, 
  search agents, and output formatters are separate classes.
- **O** — Add new retrieval strategies by subclassing, not by 
  adding if/else branches to existing classes.
- **L** — Subclasses of BaseTool must be drop-in replacements 
  (same method signatures, no narrowed inputs).
- **D** — Agent classes depend on abstractions (BaseTool, BaseRetriever), 
  never on concrete implementations directly.

When refactoring, flag any violation found and propose the fix 
before implementing.