# UI and interaction specification

## Design direction

Professional SaaS dashboard with a light neutral surface, dark readable text, one indigo accent, subtle borders and restrained shadows. Use shadcn/ui components and accessible typography. Start with 16px body text, 8px spacing units, 12px card radii and consistent 40px control heights. Support 360px mobile widths and keyboard navigation. Brand color affects the widget while dashboard navigation stays consistent.

## Information architecture

Public pages include landing, login, signup, verification, forgot/reset password and hosted chat. Owner layout has company switch/name header, setup status, profile menu and sidebar entries Overview, Knowledge, Chatbot, Conversations, Usage and Settings. V1 has one company, so do not display a nonfunctional company switcher.

| Screen | Required UI and states |
| --- | --- |
| Authentication | Email/password fields, Google button, verification banner, resend cooldown, password hints, field errors and safe reset confirmation |
| Onboarding | Company details → knowledge source → appearance/instructions → preview → publish. Save progress and allow returning later. |
| Overview | Setup checklist, ready/processing/failed sources, conversations, usage limits and primary next action |
| Knowledge list | Upload drop zone, Add website/Text/FAQ actions, source type/title/status/time, search, error and retry actions |
| Source details | Extracted text preview with pages/headings, current and pending version, stage progress, safe failure reason, replace/refresh/delete |
| Website import | URL, single-page/crawl option, crawl cap, exclusions, discovery progress and selectable discovered pages |
| Bot behavior | Instruction editor, template selector, tone/language/fallback, citation toggle and suggested questions |
| Bot appearance | Name/subtitle/logo/color/position/greeting, optional lead form, desktop/mobile live preview |
| Publish/install | Selected ready sources, unpublished-changes indicator, publish status, domain list, copy script, React/Next.js examples and hosted chat link |
| Conversations | Date/status/feedback filters, conversation list, transcript, authorized citations, lead panel, export and delete |
| Usage | Platform allowance warning, product usage, next reset when known, quota-wait explanations and no paid upgrade CTA |
| Settings | Profile, company, password, email verification, linked Google account, sign out all sessions, export and destructive deletion |

## Preview and widget

Use two columns in bot configuration with controls on the left and sticky live preview on the right. Stack on mobile. Preview clearly says Draft and uses owner authorization. Public widget says unavailable when unpublished. Preview uses the actual backend chat pipeline rather than hardcoded answer mocks once integrated.

Widget starts as a fixed chat icon. Open panel contains brand header, close control, scrollable transcript, greeting/suggestions, optional skippable lead capture and text composer. Show typing immediately, then append streamed text, preserve scroll position when visitor reads older messages, and expose Stop while generating. Disable duplicate sends. Show retry after errors and explain quota exhaustion without internal provider details. Sanitize Markdown and never render arbitrary model HTML.

Hosted chat shares widget logic in a full-page layout. Embed script adds one sandboxed iframe from our domain, validates postMessage origin and handles resize/open/close. Allowed-domain checks happen on the backend too. Use no owner credentials in script or iframe config.

## Shared behavior

Each async screen needs loading, empty, success, recoverable error and unavailable states. Use text labels alongside colored status badges. Source stage names are Uploading, Queued, Extracting, Chunking, Embedding, Indexing, Ready, Retrying, Quota paused and Failed. Show actual processing states rather than invented percentage progress.

Validate with RHF/Zod and repeat authoritative validation in FastAPI. Show inline errors near fields, reserve toast for completion notices, and require explicit confirmation plus reauthentication where appropriate for destructive account actions. Provide visible focus, accessible labels, screen-reader announcements for status changes, reduced motion and adequate contrast. Never include fake billing pages or dead navigation links.
