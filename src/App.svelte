<script lang="ts">
  import { onMount } from "svelte";
  import { getCurrentWindow } from "@tauri-apps/api/window";
  import { check } from "@tauri-apps/plugin-updater";
  import { relaunch } from "@tauri-apps/plugin-process";
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

  function safeParseJson<T>(key: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  }

  let favoriteLangs: string[] = $state(safeParseJson("lt-favorite-langs", [] as string[]));
  let recentLangs: string[] = $state(safeParseJson("lt-recent-langs", [] as string[]));

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

  let targetNotice = $derived(
    !currentModelId && statusType === "loading" ? statusMessage : ""
  );

  // Download progress for status bar (0-1)
  let initDownloadProgress = $state(0);

  // Settings model download state (lives here so closing Settings doesn't lose it)
  let settingsDownloadingId: string | null = $state(null);
  let settingsDownloadProgress: number = $state(0);
  let settingsDownloadMessage: string = $state("");
  let settingsDownloadError: string | null = $state(null);

  // TTS state
  let ttsReady = $state(false);
  let ttsStatusMessage = $state("");
  let ttsError = $state("");

  // Auto-update state
  let updateAvailable: { version: string; install: () => Promise<void> } | null = $state(null);
  let updateInstalling = $state(false);

  async function checkForUpdates() {
    try {
      const update = await check();
      if (update) {
        updateAvailable = {
          version: update.version,
          install: async () => {
            updateInstalling = true;
            try {
              await update.downloadAndInstall();
              await relaunch();
            } catch (e) {
              console.error("Update install failed:", e);
              updateInstalling = false;
            }
          },
        };
      }
    } catch (e) {
      console.error("Update check failed:", e);
    }
  }

  onMount(async () => {
    try {
      languages = await listLanguages();
      await refreshModels();

      // Check if any model is already ready (hot restart)
      if (currentModelId) {
        setStatus("ready", "Ready");
        if (sourceText.trim()) doTranslate();
        initTts();
        checkForUpdates();
        return;
      }

      // Determine which model to load
      const lastModelId = localStorage.getItem("lt-last-model") ?? "4b";
      const lastModel = models.find((m) => m.id === lastModelId);
      const anyDownloaded = models.find((m) => m.status === "downloaded");

      let targetModelId: string;
      if (lastModel && lastModel.status === "downloaded") {
        targetModelId = lastModelId;
      } else if (anyDownloaded) {
        targetModelId = anyDownloaded.id;
      } else {
        // Need to download the default model
        const fallbackId = "4b";
        const fallbackName = models.find((m) => m.id === fallbackId)?.name ?? "TranslateGemma 4B";
        setStatus("loading", `Downloading ${fallbackName}...`);
        initDownloadProgress = 0;
        await downloadModel(fallbackId, (p: DownloadProgress) => {
          initDownloadProgress = p.progress;
          statusMessage = p.message || `Downloading ${fallbackName}... ${Math.round(p.progress * 100)}%`;
        });
        initDownloadProgress = 0;
        targetModelId = fallbackId;
      }

      const targetName = models.find((m) => m.id === targetModelId)?.name ?? targetModelId;
      setStatus("loading", `Loading ${targetName}...`);
      await loadModel(targetModelId);
      await refreshModels();
      setStatus("ready", "Ready");
      if (sourceText.trim()) doTranslate();
      initTts();
      checkForUpdates();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStatus("error", msg);
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

  function saveLastModel(modelId: string) {
    localStorage.setItem("lt-last-model", modelId);
  }

  async function refreshModels() {
    models = await listModels();
    const status = await getModelStatus(models[0].id);
    currentModelId = status.currentModelId;
    if (currentModelId) {
      saveLastModel(currentModelId);
    }
  }

  async function handleSettingsDownload(modelId: string) {
    settingsDownloadingId = modelId;
    settingsDownloadProgress = 0;
    settingsDownloadMessage = "Starting download...";
    settingsDownloadError = null;
    try {
      await downloadModel(modelId, (p: DownloadProgress) => {
        settingsDownloadProgress = p.progress;
        settingsDownloadMessage = p.message;
      });
      await refreshModels();
    } catch (e: unknown) {
      settingsDownloadError = e instanceof Error ? e.message : String(e);
      try { await refreshModels(); } catch { /* best effort */ }
    } finally {
      settingsDownloadingId = null;
    }
  }

  function handleSettingsOpen() {
    settingsOpen = true;
    // Refresh model list so reopened Settings shows current state
    refreshModels();
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
      if (statusType === "error") {
        setStatus("ready", "Ready");
      }
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

<!-- svelte-ignore a11y_no_noninteractive_element_interactions, a11y_no_static_element_interactions -->
<header class="app-header" onmousedown={(e) => { if (e.button === 0 && e.detail === 1) getCurrentWindow().startDragging(); }}>
  <div class="header-spacer"></div>
  <h1 class="app-title">Local Translate</h1>
  <div class="header-right">
    <button class="settings-btn" onmousedown={(e) => e.stopPropagation()} onclick={handleSettingsOpen} title="Settings">
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
    maxlength={5000}
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
    notice={targetNotice}
    noticeProgress={initDownloadProgress > 0 ? initDownloadProgress : -1}
    placeholder="Translation will appear here..."
    onlangchange={handleTargetLangChange}
    ontogglefavorite={toggleFavorite}
  />
</main>

<footer class="status-bar">
  <span class="status-indicator" class:ready={statusType === "ready"} class:error={statusType === "error"} class:loading={statusType === "loading"}></span>
  {#if initDownloadProgress > 0 && initDownloadProgress < 1}
    <div class="status-progress-bar">
      <div class="status-progress-fill" style="width: {initDownloadProgress * 100}%"></div>
    </div>
  {/if}
  <span class="status-text">{ttsStatusMessage || statusMessage}</span>
  {#if updateAvailable}
    <button class="update-banner" onclick={updateAvailable.install} disabled={updateInstalling}>
      {#if updateInstalling}
        Installing update...
      {:else}
        Update v{updateAvailable.version} available — click to install
      {/if}
    </button>
  {/if}
  {#if currentModelId}
    <span class="status-model">TranslateGemma {currentModelId.toUpperCase()}</span>
  {/if}
</footer>

<Settings
  open={settingsOpen}
  {models}
  {currentModelId}
  downloadingId={settingsDownloadingId}
  downloadProgress={settingsDownloadProgress}
  downloadMessage={settingsDownloadMessage}
  downloadError={settingsDownloadError}
  {updateAvailable}
  {updateInstalling}
  onclose={() => (settingsOpen = false)}
  onmodelschange={refreshModels}
  ondownload={handleSettingsDownload}
  oncheckupdate={checkForUpdates}
/>

<style>
  /* Header — macOS-style toolbar */
  .app-header {
    display: flex;
    align-items: center;
    height: 52px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
    -webkit-user-select: none;
    user-select: none;
    cursor: default;
    position: relative;
  }

  .app-title {
    font-size: 0.8125rem;
    font-weight: 500;
    letter-spacing: 0;
    margin: 0;
    color: var(--text-secondary);
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
    pointer-events: none;
  }

  .header-spacer {
    flex: 1;
  }

  .header-right {
    display: flex;
    align-items: center;
    padding-right: 1rem;
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

  .status-indicator.loading {
    background: #6366f1;
    animation: pulse 1.2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }

  .status-progress-bar {
    width: 80px;
    height: 4px;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 2px;
    overflow: hidden;
    flex-shrink: 0;
  }

  .status-progress-fill {
    height: 100%;
    background: #6366f1;
    border-radius: 2px;
    transition: width 0.3s;
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

  .update-banner {
    background: rgba(99, 102, 241, 0.15);
    color: #818cf8;
    border: 1px solid rgba(99, 102, 241, 0.3);
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 0.7rem;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.15s, border-color 0.15s;
  }

  .update-banner:hover:not(:disabled) {
    background: rgba(99, 102, 241, 0.25);
    border-color: rgba(99, 102, 241, 0.5);
  }

  .update-banner:disabled {
    opacity: 0.7;
    cursor: default;
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
