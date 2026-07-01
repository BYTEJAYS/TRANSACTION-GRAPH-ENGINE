---
paths:
  - "src/components/**"
  - "src/pages/**"
  - "src/app/**"
  - "components/**"
  - "pages/**"
  - "app/**/*.tsx"
  - "app/**/*.jsx"
  - "**/*.tsx"
  - "**/*.jsx"
---

# Frontend Rules

## Components
- Functional components with hooks only — no class components
- One component per file — name matches filename exactly
- Props must be typed (TypeScript interface or type, not `any`)
- Default props via destructuring defaults, not defaultProps
- Keep components under 150 lines — if longer, extract child components

## State Management
- Local state: useState/useReducer for component-only state
- Global state: use the project's state library (check project CLAUDE.md)
- No prop drilling beyond 2 levels — use context or global state
- Derived state: compute from existing state, don't duplicate

## Styling
- Use the project's CSS system (Tailwind / CSS Modules / styled-components — check CLAUDE.md)
- No inline styles except for truly dynamic values (e.g., calculated widths)
- Dark mode considered for every color decision
- Responsive by default — mobile-first

## Performance
- No anonymous functions in JSX (creates new reference every render)
- useCallback/useMemo only when there's a measurable performance problem — not by default
- Images: use the project's image component (next/image or equivalent)
- Lazy load components not needed on initial render

## Accessibility
- Interactive elements are keyboard navigable
- Images have meaningful alt text (not "image" or filename)
- Form inputs have associated labels (not just placeholders)
- Color is not the only way to convey information

## Security & Safety
- Error boundaries wrapping every major route or feature area — never let one component crash the whole app
- No inline event handlers that reference user-controlled content (XSS vector)
- CSP-safe: no `eval()`, no inline `<script>` tags in JSX, no `dangerouslySetInnerHTML` with unsanitized data

## Patterns
- Conditional rendering: ternary for simple, extracted component for complex
- Lists always have stable, unique keys — never array index as key
- Event handlers named `handle[Event]` (e.g., `handleSubmit`, `handleClick`)
- Loading/error/empty states handled for every async operation
