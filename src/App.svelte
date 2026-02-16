<script lang="ts">
  import { onMount } from "svelte";
  import TranslatePanel from "./lib/TranslatePanel.svelte";
  import Settings from "./lib/Settings.svelte";
  import {
    listLanguages,
    listModels,
    translate,
    getModelStatus,
    downloadModel,
    loadModel,
    getTtsStatus,
    downloadTtsModel,
    loadTtsModel,
    type LanguageInfo,
    type ModelInfo,
    type DownloadProgress,
  } from "./lib/api";

  let languages: LanguageInfo[] = $state([]);
  let models: ModelInfo[] = $state([]);
  let currentModelId: string | null = $state(null);

  let sourceLang = $state("en");
  let targetLang = $state("es");
  let sourceText = $state("");
  let targetText = $state("");

  let favoriteLangs: string[] = $state(
    JSON.parse(localStorage.getItem("lt-favorite-langs") || "[]")
  );
  let recentLangs: string[] = $state(
    JSON.parse(localStorage.getItem("lt-recent-langs") || "[]")
  );

  function pushRecent(code: string) {
    recentLangs = [code, ...recentLangs.filter((c) => c !== code)].slice(0, 5);
    localStorage.setItem("lt-recent-langs", JSON.stringify(recentLangs));
  }

  function toggleFavorite(code: string) {
    if (favoriteLangs.includes(code)) {
      favoriteLangs = favoriteLangs.filter((c) => c !== code);
    } else {
      favoriteLangs = [...favoriteLangs, code];
    }
    localStorage.setItem("lt-favorite-langs", JSON.stringify(favoriteLangs));
  }

  let translating = $state(false);
  let settingsOpen = $state(false);
  let statusMessage = $state("Loading...");
  let statusType: "info" | "loading" | "ready" | "error" = $state("loading");

  let translateTimer: ReturnType<typeof setTimeout> | null = null;

  // First-launch flow state
  let initializing = $state(true);
  let initDownloading = $state(false);
  let initDownloadProgress = $state(0);
  let initDownloadMessage = $state("");
  let initLoading = $state(false);

  // TTS state
  let ttsReady = $state(false);
  let ttsStatusMessage = $state("");
  let ttsError = $state("");

  onMount(async () => {
    try {
      languages = await listLanguages();
      await refreshModels();

      // Check if any model is ready
      if (currentModelId) {
        setStatus("ready", "Ready");
        initializing = false;
        initTts();
        return;
      }

      // Check if default model is downloaded but not loaded
      const defaultModel = models.find((m) => m.id === "4b");
      if (defaultModel && defaultModel.status === "downloaded") {
        setStatus("loading", "Loading model...");
        initLoading = true;
        await loadModel("4b");
        await refreshModels();
        initLoading = false;
        setStatus("ready", "Ready");
        initializing = false;
        initTts();
        return;
      }

      // Need to download
      setStatus("loading", "Downloading model...");
      initDownloading = true;
      await downloadModel("4b", (p: DownloadProgress) => {
        initDownloadProgress = p.progress;
        initDownloadMessage = p.message;
      });
      initDownloading = false;

      setStatus("loading", "Loading model...");
      initLoading = true;
      await loadModel("4b");
      await refreshModels();
      initLoading = false;
      setStatus("ready", "Ready");
      initializing = false;
      initTts();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus("error", msg);
      initializing = false;
    }
  });

  function setStatus(type: typeof statusType, message: string) {
    statusType = type;
    statusMessage = message;
  }

  async function initTts() {
    try {
      ttsError = "";
      const status = await getTtsStatus();
      if (status.status === "ready") {
        ttsReady = true;
        return;
      }

      if (status.status !== "downloaded") {
        ttsStatusMessage = "Downloading TTS model...";
        await downloadTtsModel((p: DownloadProgress) => {
          ttsStatusMessage = `Downloading TTS model... ${Math.round(p.progress * 100)}%`;
        });
      }

      ttsStatusMessage = "Loading TTS model...";
      await loadTtsModel();
      ttsReady = true;
      ttsStatusMessage = "";
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error("TTS init failed:", msg);
      ttsError = msg;
      ttsStatusMessage = "";
    }
  }

  async function refreshModels() {
    models = await listModels();
    const status = await getModelStatus("4b");
    currentModelId = status.currentModelId;
    // Also check other models
    for (const m of models) {
      if (m.status === "ready") {
        currentModelId = m.id;
      }
    }
  }

  function handleSourceTextChange(text: string) {
    sourceText = text;
    if (translateTimer) clearTimeout(translateTimer);
    if (!text.trim()) {
      targetText = "";
      return;
    }
    translateTimer = setTimeout(() => doTranslate(), 500);
  }

  async function doTranslate() {
    if (!sourceText.trim() || !currentModelId) return;
    translating = true;
    try {
      targetText = await translate(sourceText, sourceLang, targetLang);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus("error", msg);
    } finally {
      translating = false;
    }
  }

  function handleSourceLangChange(code: string) {
    sourceLang = code;
    pushRecent(code);
    if (sourceText.trim()) {
      if (translateTimer) clearTimeout(translateTimer);
      translateTimer = setTimeout(() => doTranslate(), 300);
    }
  }

  function handleTargetLangChange(code: string) {
    targetLang = code;
    pushRecent(code);
    if (sourceText.trim()) {
      if (translateTimer) clearTimeout(translateTimer);
      translateTimer = setTimeout(() => doTranslate(), 300);
    }
  }

  function swapLanguages() {
    const tmpLang = sourceLang;
    const tmpText = sourceText;
    sourceLang = targetLang;
    targetLang = tmpLang;
    sourceText = targetText;
    targetText = tmpText;
    if (sourceText.trim()) {
      if (translateTimer) clearTimeout(translateTimer);
      translateTimer = setTimeout(() => doTranslate(), 300);
    }
  }
</script>

{#if initializing}
  <div class="init-screen">
    <div class="init-content">
      <h1 class="init-title">Local Translate</h1>
      <p class="init-subtitle">Private, offline translation powered by TranslateGemma</p>

      {#if initDownloading}
        <div class="init-step">
          <div class="init-step-label">Downloading TranslateGemma 4B...</div>
          <div class="init-progress-bar">
            <div class="init-progress-fill" style="width: {initDownloadProgress * 100}%"></div>
          </div>
          <div class="init-progress-text">{initDownloadMessage}</div>
        </div>
      {:else if initLoading}
        <div class="init-step">
          <div class="init-step-label">Loading model...</div>
          <div class="init-spinner"></div>
        </div>
      {:else if statusType === "error"}
        <div class="init-step">
          <div class="init-error">{statusMessage}</div>
        </div>
      {:else}
        <div class="init-step">
          <div class="init-spinner"></div>
        </div>
      {/if}
    </div>
  </div>
{:else}
  <header class="app-header">
    <div class="header-left">
      <h1 class="app-title">Local Translate</h1>
    </div>
    <div class="header-right">
      <button class="settings-btn" onclick={() => (settingsOpen = true)} title="Settings">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
        </svg>
      </button>
    </div>
  </header>

  <main class="translate-container">
    <TranslatePanel
      {languages}
      lang={sourceLang}
      text={sourceText}
      favorites={favoriteLangs}
      recents={recentLangs}
      {ttsReady}
      {ttsError}
      placeholder="Enter text to translate..."
      onlangchange={handleSourceLangChange}
      ontextchange={handleSourceTextChange}
      ontogglefavorite={toggleFavorite}
    />

    <div class="divider">
      <button class="swap-btn" onclick={swapLanguages} title="Swap languages">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="17 1 21 5 17 9"></polyline>
          <path d="M3 11V9a4 4 0 0 1 4-4h14"></path>
          <polyline points="7 23 3 19 7 15"></polyline>
          <path d="M21 13v2a4 4 0 0 1-4 4H3"></path>
        </svg>
      </button>
    </div>

    <TranslatePanel
      {languages}
      lang={targetLang}
      text={targetText}
      favorites={favoriteLangs}
      recents={recentLangs}
      {ttsReady}
      {ttsError}
      readonly
      loading={translating}
      placeholder="Translation will appear here..."
      onlangchange={handleTargetLangChange}
      ontogglefavorite={toggleFavorite}
    />
  </main>

  <footer class="status-bar">
    <span class="status-indicator" class:ready={statusType === "ready"} class:error={statusType === "error"}></span>
    <span class="status-text">{ttsStatusMessage || statusMessage}</span>
    {#if currentModelId}
      <span class="status-model">TranslateGemma {currentModelId.toUpperCase()}</span>
    {/if}
  </footer>

  <Settings
    open={settingsOpen}
    {models}
    {currentModelId}
    onclose={() => (settingsOpen = false)}
    onmodelschange={refreshModels}
  />
{/if}

<style>
  /* Init / first-launch screen */
  .init-screen {
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .init-content {
    text-align: center;
    max-width: 400px;
    padding: 2rem;
  }

  .init-title {
    font-size: 2rem;
    font-weight: 600;
    letter-spacing: -0.03em;
    color: #ededed;
    margin: 0 0 0.5rem 0;
  }

  .init-subtitle {
    color: #888;
    font-size: 1rem;
    margin: 0 0 2.5rem 0;
  }

  .init-step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
  }

  .init-step-label {
    color: #888;
    font-size: 0.875rem;
  }

  .init-progress-bar {
    width: 100%;
    height: 6px;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 3px;
    overflow: hidden;
  }

  .init-progress-fill {
    height: 100%;
    background: #6366f1;
    border-radius: 3px;
    transition: width 0.3s;
  }

  .init-progress-text {
    font-size: 0.8rem;
    color: #555;
  }

  .init-spinner {
    width: 24px;
    height: 24px;
    border: 3px solid rgba(255, 255, 255, 0.06);
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  .init-error {
    color: #ef4444;
    font-size: 0.875rem;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* Header */
  .app-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.25rem;
    height: 52px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .app-title {
    font-size: 0.95rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    margin: 0;
    color: #ededed;
  }

  .header-left, .header-right {
    display: flex;
    align-items: center;
  }

  .settings-btn {
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
  }

  .settings-btn:hover {
    color: #ededed;
    background: rgba(255, 255, 255, 0.04);
  }

  /* Main translate area */
  .translate-container {
    flex: 1;
    display: flex;
    min-height: 0;
  }

  .divider {
    width: 1px;
    background: var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    flex-shrink: 0;
  }

  .swap-btn {
    position: absolute;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 1px solid var(--border);
    background: var(--surface);
    color: #888;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s, border-color 0.15s, background 0.15s;
    z-index: 1;
  }

  .swap-btn:hover {
    color: #ededed;
    border-color: rgba(255, 255, 255, 0.15);
    background: var(--surface-hover);
  }

  /* Status bar */
  .status-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 1.25rem;
    height: 32px;
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: #555;
    flex-shrink: 0;
  }

  .status-indicator {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #555;
    flex-shrink: 0;
  }

  .status-indicator.ready {
    background: #22c55e;
  }

  .status-indicator.error {
    background: #ef4444;
  }

  .status-text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .status-model {
    color: #888;
    flex-shrink: 0;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .translate-container {
      flex-direction: column;
    }

    .divider {
      width: auto;
      height: 1px;
      flex-direction: row;
    }

    .swap-btn {
      position: static;
    }
  }
</style>
