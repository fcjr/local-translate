<script lang="ts">
  import LanguageSelector from "./LanguageSelector.svelte";
  import type { LanguageInfo } from "./api";

  interface Props {
    languages: LanguageInfo[];
    lang: string;
    text: string;
    favorites: string[];
    recents: string[];
    readonly?: boolean;
    loading?: boolean;
    placeholder?: string;
    onlangchange: (code: string) => void;
    ontextchange?: (text: string) => void;
    ontogglefavorite: (code: string) => void;
  }

  let {
    languages,
    lang,
    text,
    favorites,
    recents,
    readonly = false,
    loading = false,
    placeholder = "",
    onlangchange,
    ontextchange,
    ontogglefavorite,
  }: Props = $props();
</script>

<div class="panel">
  <div class="panel-header">
    <LanguageSelector {languages} value={lang} {favorites} {recents} onchange={onlangchange} {ontogglefavorite} />
  </div>
  <div class="textarea-wrapper">
    <textarea
      class="panel-textarea"
      value={text}
      {readonly}
      {placeholder}
      oninput={(e) => ontextchange?.(e.currentTarget.value)}
    ></textarea>
    {#if loading}
      <div class="loading-overlay">
        <div class="spinner"></div>
        <span>Translating...</span>
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

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
