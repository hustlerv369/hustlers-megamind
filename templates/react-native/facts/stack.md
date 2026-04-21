---
name: Stack overview
type: fact
date: YYYY-MM-DD
---

# Stack

| Layer | Choice | Version | Notes |
|-------|--------|---------|-------|
| Framework | React Native | | |
| Managed by | Expo / bare RN | | |
| Expo SDK | | | |
| Navigator | Expo Router / React Navigation | | |
| State | Zustand / Redux / Jotai / ? | | |
| API client | TanStack Query / RTK Query / ? | | |
| Auth | Clerk / Firebase / custom | | |
| Storage | AsyncStorage / MMKV / SQLite | | |
| Analytics | | | |
| Error reporting | Sentry / Bugsnag | | |

## Commands
- `npx expo start` — dev server
- `eas build --profile preview --platform ios` — build preview
- `eas submit` — submit to store
