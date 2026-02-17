<script lang="ts">
  import LanguageSelector from "./LanguageSelector.svelte";
  import type { LanguageInfo } from "./api";
  import { synthesizeSpeech } from "./api";

  interface Props {
    languages: LanguageInfo[];
    lang: string;
    text: string;
    favorites: string[];
    recents: string[];
    ttsReady?: boolean;
    ttsError?: string;
    readonly?: boolean;
    loading?: boolean;
    notice?: string;
    noticeProgress?: number;
    placeholder?: string;
    onlangchange: (code: string) => void;
    ontextchange?: (text: string) => void;
    ontogglefavorite: (code: string) => void;
    maxlength?: number;
  }

  let {
    languages,
    lang,
    text,
    favorites,
    recents,
    ttsReady = false,
    ttsError = "",
    readonly = false,
    loading = false,
    notice = "",
    noticeProgress = -1,
    placeholder = "",
    onlangchange,
    ontextchange,
    ontogglefavorite,
    maxlength,
  }: Props = $props();

  const TTS_SUPPORTED_LANGS = new Set([
    "zh", "en", "ja", "ko", "de", "fr", "ru", "pt", "es", "it",
  ]);

  type TtsState = "idle" | "loading" | "playing" | "error";
  let ttsState: TtsState = $state("idle");
  let ttsErrorMsg = $state("");
  let currentAudio: HTMLAudioElement | null = null;
  let currentAudioUrl: string | null = null;

  let langSupported = $derived(TTS_SUPPORTED_LANGS.has(lang));

  let ttsDisabled = $derived(
    !ttsReady || !langSupported || !text.trim() || ttsState === "loading" || ttsState === "error"
  );

  let ttsTooltip = $derived.by(() => {
    if (ttsState === "playing") return "Stop playback";
    if (ttsState === "loading") return "Generating speech...";
    if (ttsState === "error") return `Speech failed: ${ttsErrorMsg}`;
    if (ttsError) return `TTS unavailable: ${ttsError}`;
    if (!ttsReady) return "TTS model is loading...";
    if (!langSupported) {
      const langName = languages.find((l) => l.code === lang)?.name ?? lang;
      return `Text-to-speech is not available for ${langName}`;
    }
    if (!text.trim()) return "Enter text to listen";
    return "Listen";
  });

  async function handleTtsClick() {
    if (ttsState === "playing") {
      stopAudio();
      return;
    }
    if (ttsDisabled) return;

    ttsState = "loading";
    try {
      const wavB64 = await synthesizeSpeech(text, lang);

      const bytes = Uint8Array.from(atob(wavB64), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: "audio/wav" });
      const url = URL.createObjectURL(blob);

      const audio = new Audio(url);
      currentAudio = audio;
      currentAudioUrl = url;
      ttsState = "playing";

      audio.onended = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        currentAudioUrl = null;
        ttsState = "idle";
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        currentAudio = null;
        currentAudioUrl = null;
        ttsState = "idle";
      };
      audio.play();
    } catch (e: unknown) {
      ttsErrorMsg = e instanceof Error ? e.message : "Speech synthesis failed";
      ttsState = "error";
      setTimeout(() => {
        if (ttsState === "error") ttsState = "idle";
      }, 3000);
    }
  }

  function stopAudio() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    if (currentAudioUrl) {
      URL.revokeObjectURL(currentAudioUrl);
      currentAudioUrl = null;
    }
    ttsState = "idle";
  }
</script>

<div class="panel">
  <div class="panel-header">
    <LanguageSelector {languages} value={lang} {favorites} {recents} onchange={onlangchange} {ontogglefavorite} />
    <button
      class="tts-btn"
      class:playing={ttsState === "playing"}
      class:error={ttsState === "error"}
      disabled={ttsDisabled && ttsState !== "playing"}
      title={ttsTooltip}
      onclick={handleTtsClick}
    >
      {#if ttsState === "error"}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f87171" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="15" y1="9" x2="9" y2="15"></line>
          <line x1="9" y1="9" x2="15" y2="15"></line>
        </svg>
      {:else if ttsState === "loading"}
        <svg class="tts-spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"></circle>
        </svg>
      {:else if ttsState === "playing"}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="none">
          <rect x="6" y="5" width="4" height="14" rx="1"></rect>
          <rect x="14" y="5" width="4" height="14" rx="1"></rect>
        </svg>
      {:else}
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
          <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
        </svg>
      {/if}
    </button>
  </div>
  <div class="textarea-wrapper">
    <textarea
      class="panel-textarea"
      value={text}
      {readonly}
      {placeholder}
      maxlength={readonly ? undefined : maxlength}
      oninput={(e) => ontextchange?.(e.currentTarget.value)}
    ></textarea>
    {#if loading}
      <div class="loading-overlay">
        <div class="spinner"></div>
        <span>Translating...</span>
      </div>
    {:else if notice && !text}
      <div class="notice-overlay">
        <div class="notice-card">
          <div class="notice-spinner"></div>
          <span class="notice-text">{notice}</span>
          {#if noticeProgress >= 0 && noticeProgress < 1}
            <div class="notice-progress">
              <div class="notice-progress-fill" style="width: {noticeProgress * 100}%"></div>
            </div>
          {/if}
        </div>
      </div>
    {/if}
  </div>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
  }

  .panel-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .tts-btn {
    background: none;
    border: none;
    color: #888;
    cursor: pointer;
    padding: 6px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s, background 0.15s;
    flex-shrink: 0;
  }

  .tts-btn:hover:not(:disabled) {
    color: #ededed;
    background: rgba(255, 255, 255, 0.04);
  }

  .tts-btn:disabled {
    opacity: 0.3;
    cursor: default;
  }

  .tts-btn.playing {
    color: var(--accent, #6366f1);
  }

  .tts-btn.error {
    color: #f87171;
    opacity: 1;
  }

  .tts-spinner {
    animation: spin 0.8s linear infinite;
  }

  .textarea-wrapper {
    position: relative;
    flex: 1;
    display: flex;
  }

  .panel-textarea {
    flex: 1;
    border: none;
    padding: 16px;
    font-size: 16px;
    line-height: 1.6;
    resize: none;
    background: transparent;
    color: var(--text);
    font-family: inherit;
  }

  .panel-textarea:focus {
    outline: none;
  }

  .panel-textarea[readonly] {
    cursor: default;
  }

  .loading-overlay {
    position: absolute;
    inset: 0;
    background: rgba(10, 10, 11, 0.85);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--text-secondary);
    font-size: 14px;
  }

  .spinner {
    width: 24px;
    height: 24px;
    border: 3px solid var(--border);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .notice-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }

  .notice-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    padding: 24px 32px;
    border-radius: 12px;
    background: rgba(99, 102, 241, 0.06);
    border: 1px solid rgba(99, 102, 241, 0.12);
  }

  .notice-spinner {
    width: 28px;
    height: 28px;
    border: 2.5px solid rgba(99, 102, 241, 0.2);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }

  .notice-text {
    color: var(--text-secondary);
    font-size: 13px;
    font-weight: 500;
  }

  .notice-progress {
    width: 140px;
    height: 4px;
    background: rgba(99, 102, 241, 0.12);
    border-radius: 2px;
    overflow: hidden;
  }

  .notice-progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.3s;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
