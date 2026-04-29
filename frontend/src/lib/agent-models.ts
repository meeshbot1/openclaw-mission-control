export const MODEL_PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "google", label: "Google (Gemini)" },
  { value: "anthropic", label: "Anthropic (Claude)" },
  { value: "ollama", label: "Ollama (Local)" },
] as const;

export const DEFAULT_MODEL_PROVIDER = "openai";
