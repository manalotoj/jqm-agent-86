export type ComposerModel = "gpt-4.1-mini" | "gpt-5.4";

export type ComposerPreferences = {
  selectedModel: ComposerModel;
  webSearchEnabled: boolean;
};

const DEFAULT_PREFERENCES: ComposerPreferences = {
  selectedModel: "gpt-4.1-mini",
  webSearchEnabled: false,
};
const STORAGE_KEY_PREFIX = "agent-86:composer-preferences:v1:";

function getStorageKey(userId: string) {
  return `${STORAGE_KEY_PREFIX}${encodeURIComponent(userId)}`;
}

function isComposerModel(value: unknown): value is ComposerModel {
  return value === "gpt-4.1-mini" || value === "gpt-5.4";
}

export function loadComposerPreferences(userId: string): ComposerPreferences {
  try {
    const value = localStorage.getItem(getStorageKey(userId));

    if (!value) {
      return DEFAULT_PREFERENCES;
    }

    const parsed: unknown = JSON.parse(value);

    if (!parsed || typeof parsed !== "object") {
      return DEFAULT_PREFERENCES;
    }

    const preferences = parsed as Partial<ComposerPreferences>;

    return {
      selectedModel: isComposerModel(preferences.selectedModel)
        ? preferences.selectedModel
        : DEFAULT_PREFERENCES.selectedModel,
      webSearchEnabled:
        typeof preferences.webSearchEnabled === "boolean"
          ? preferences.webSearchEnabled
          : DEFAULT_PREFERENCES.webSearchEnabled,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

export function saveComposerPreferences(userId: string, preferences: ComposerPreferences) {
  try {
    localStorage.setItem(getStorageKey(userId), JSON.stringify(preferences));
  } catch {
    // Preferences remain usable for the current page when storage is unavailable.
  }
}