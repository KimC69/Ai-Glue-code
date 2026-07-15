# [Project name]

_Replace the heading above with the project's name, and this line with one sentence describing what this app does for users._

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `cd agents/mobile-apk && nix-shell shell.nix --run 'python build_apk.py --api-url http://<IP>:8000'` — build the Android APK from the PWA
- Required env: `DATABASE_URL` — Postgres connection string

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)
- Mobile APK: Capacitor 6 + JDK 17 + Android SDK 34 (managed via `agents/mobile-apk/shell.nix`)

## Where things live

- `agents/` — Python multi-agent film pipeline (CLI, API server, PWA, desktop app, mobile APK builder)
- `agents/mobile-apk/` — Capacitor project that packages the PWA into an installable Android APK; see `agents/mobile-apk/README.md` for full developer docs
- `agents/pwa/` — Progressive Web App served statically by the API server
- `artifacts/api-server/` — Replit-managed Express API server artifact
- `artifacts/mockup-sandbox/` — Replit-managed canvas/design mockup artifact

## Architecture decisions

_Populate as you build — non-obvious choices a reader couldn't infer from the code (3-5 bullets)._

## Product

_Describe the high-level user-facing capabilities of this app once they exist._

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

_Populate as you build — sharp edges, "always run X before Y" rules._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
