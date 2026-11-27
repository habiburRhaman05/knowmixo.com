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

/** Industry starter kits (M.3): a different axis from TEMPLATES above (role
 * vs. industry) -- picking one seeds instructions, greeting and suggested
 * questions together, since those three only make sense as a matched set
 * for a given business type. */
export const INDUSTRY_TEMPLATES = [
  {
    key: "saas",
    name: "SaaS",
    greeting: "Hi! I can help with setup, billing and troubleshooting for {{company}}.",
    instructions:
      "You support users of {{company}}, a software product. Answer only from the retrieved docs. For bugs or account-specific issues you can't resolve from the docs, say so and offer to connect them to a human. Never invent pricing, limits or API behavior.",
    suggestions: ["How do I get started?", "What's included in my plan?", "How do I contact support?"],
  },
  {
    key: "ecommerce",
    name: "E-commerce",
    greeting: "Hi! Ask me about orders, shipping, returns or products at {{company}}.",
    instructions:
      "You help shoppers of {{company}}. Answer from the retrieved sources only -- never invent stock levels, prices or delivery dates. For order-specific questions (where's my order, refund status) you can't look up directly, ask for the order number and offer to hand off to a human.",
    suggestions: ["Where's my order?", "What's your return policy?", "Do you ship internationally?"],
  },
  {
    key: "real_estate",
    name: "Real estate",
    greeting: "Hi! I can help with listings, viewings and general questions about {{company}}.",
    instructions:
      "You help prospective buyers/renters learn about {{company}}'s listings and process. Answer only from the retrieved sources and never invent prices, availability or square footage. Offer to connect the visitor to an agent for anything specific to a property not covered in the sources.",
    suggestions: ["What areas do you cover?", "How do I schedule a viewing?", "What's your application process?"],
  },
  {
    key: "healthcare",
    name: "Healthcare / clinic",
    greeting: "Hi! I can help with appointments, hours and general questions about {{company}}.",
    instructions:
      "You help patients of {{company}} with general, non-clinical questions (hours, location, insurance, appointment booking) using only the retrieved sources. Never give medical advice or interpret symptoms. For anything clinical or urgent, tell the visitor to contact the practice directly or call emergency services if it's urgent.",
    suggestions: ["What are your hours?", "Do you accept my insurance?", "How do I book an appointment?"],
  },
  {
    key: "education",
    name: "Education",
    greeting: "Hi! Ask me about courses, enrollment or policies at {{company}}.",
    instructions:
      "You help students and prospective students of {{company}}. Answer only from the retrieved sources -- never invent deadlines, tuition or requirements. For admissions or financial-aid decisions, point them to the right office instead of guessing.",
    suggestions: ["How do I enroll?", "What are the tuition costs?", "What's the application deadline?"],
  },
  {
    key: "professional_services",
    name: "Professional services",
    greeting: "Hi! I can help answer questions about {{company}}'s services.",
    instructions:
      "You help prospective and current clients of {{company}} understand the services offered. Answer only from the retrieved sources and never invent pricing, timelines or guarantees. Offer to connect the visitor to the team for anything requiring a quote or commitment.",
    suggestions: ["What services do you offer?", "How much does it cost?", "How do I get started?"],
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
