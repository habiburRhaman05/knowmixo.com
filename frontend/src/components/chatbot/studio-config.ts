/** Default draft config written when the backend returns an empty object. */
export const DEFAULT_CONFIG = {
  name: "Assistant",
  tone: "helpful",
  language: "en",
  fallback_message: "I couldn't find an answer to that in the available information.",
  greeting: "Hi! Ask me anything about our docs and site.",
  instructions: "",
  suggestions: [] as string[],
  citations_enabled: true,
  branding: {
    color: "#4f46e5",
    position: "bottom-right" as "bottom-right" | "bottom-left",
  },
};

export type DraftConfig = typeof DEFAULT_CONFIG;

export const TONE_OPTIONS = [
  { value: "helpful", label: "Helpful" },
  { value: "friendly", label: "Friendly" },
  { value: "formal", label: "Formal" },
  { value: "concise", label: "Concise" },
  { value: "playful", label: "Playful" },
];

export const LANGUAGE_OPTIONS = [
  { value: "en", label: "English" },
  { value: "bn", label: "Bangla" },
  { value: "es", label: "Spanish" },
  { value: "fr", label: "French" },
  { value: "de", label: "German" },
];

export const TEMPLATES = [
  {
    key: "support",
    name: "Customer support",
    instructions:
      "You help customers of {{company}}. Answer only from the retrieved sources. When the answer isn't there, say so and suggest contacting support. Keep replies under 120 words unless the user asks for detail.",
  },
  {
    key: "sales",
    name: "Sales assistant",
    instructions:
      "You help prospects understand {{company}}. Explain features and pricing clearly, cite source pages, and never invent SLAs, prices or dates. Ask follow-up questions when the user's need is unclear.",
  },
  {
    key: "internal",
    name: "Internal helpdesk",
    instructions:
      "You help employees find internal policies. Use a neutral, professional tone. If a question needs human approval, tell the user and name the owning team if the sources identify it.",
  },
];

/**
 * Compute a shallow diff between the current and last-saved config so we
 * can PATCH only the keys that actually changed.
 */
export function diffConfig(current: DraftConfig, prev: DraftConfig): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  (Object.keys(current) as Array<keyof DraftConfig>).forEach((key) => {
    const a = current[key];
    const b = prev[key];
    if (JSON.stringify(a) !== JSON.stringify(b)) {
      patch[key] = a;
    }
  });
  return patch;
}
