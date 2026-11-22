# Acceptance criteria

| Feature | Required acceptance checks |
| --- | --- |
| A Authentication | Duplicate signup returns safe behavior. Unverified password accounts cannot publish or chat as owner. Expired, reused and invalid verification/reset tokens fail. Google audience, issuer, expiry and verified email are validated. Existing email does not silently link accounts. Logout-all immediately blocks old backend tokens. |
| B Profile/company | Only the owner can modify their company. Email changes require verification and appropriate reauthentication. Account deletion revokes sessions and publication immediately, then tracks complete storage/vector cleanup. |
| C Dashboard | Counts come from authorized API data. Empty, loading, failed, paused-quota and completed states render. Usage is clearly platform-limited. |
| D Sources | Each supported file format and source type has a fixture. MIME/signature/size are checked. URL import blocks local and internal targets, including redirects. Crawl is capped, same-domain and respects robots directives. |
| E Processing | UI never reports ready before the complete source version is searchable. Restarted workers resume safely. Manual replay of a dead job cannot duplicate active chunks. Removing a source excludes it immediately even if physical vector cleanup is pending. |
| F Bot behavior | Saved instructions affect preview and only affect public chat after publish. Instructions cannot grant access or override tenant boundaries. Unknown answers use configured fallback. |
| G Branding | Color, greeting, placement and suggestions preview accurately. Invalid colors and oversized images are rejected. Lead capture is skippable and consent text explains storage. |
| H Publishing | Publish requires a ready selected source. Publication stores a consistent snapshot. Unpublish blocks new visitor sessions and subsequent requests immediately. A draft replacement never leaks into the active snapshot. |
| I Embed | Script works on plain HTML, React and Next.js test pages. Loading twice creates one widget. Domain restrictions are enforced server-side and are described as abuse reduction, not visitor authentication. |
| J Chat | Cache hit and miss follow identical authorization. Ordered streamed events include a terminal done/error event when connected. Stop/disconnect cancels upstream generation. Errors preserve an interrupted transcript without marking it completed. |
| K History | Owner cannot retrieve another owner's conversation by changing an ID. Feedback references a real accessible assistant message. Export excludes secrets. Deletion removes related messages, leads and cached answers. |
| L Operations | Temporary failures retry with bounded backoff. Permanent failures go to dead state. Quota errors defer. Redis loss does not lose a committed job. Restore drill succeeds. Provider keys never appear in browser requests or logs. |

Each test result records fixture, expected result, actual result and evidence. Any failed authorization, secret leakage or paid fallback check blocks launch.
