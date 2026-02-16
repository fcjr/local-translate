<script lang="ts">
  import type { ModelInfo, DownloadProgress } from "./api";
  import { downloadModel, loadModel } from "./api";

  interface Props {
    open: boolean;
    models: ModelInfo[];
    currentModelId: string | null;
    onclose: () => void;
    onmodelschange: () => void;
  }

  let { open, models, currentModelId, onclose, onmodelschange }: Props =
    $props();

  let downloadingId: string | null = $state(null);
  let downloadProgress: number = $state(0);
  let downloadMessage: string = $state("");
  let loadingId: string | null = $state(null);
  let error: string | null = $state(null);

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape" && open) {
      onclose();
    }
  }

  $effect(() => {
    if (open) {
      document.addEventListener("keydown", handleKeydown);
    }
    return () => {
      document.removeEventListener("keydown", handleKeydown);
    };
  });

  async function handleDownload(modelId: string) {
    downloadingId = modelId;
    downloadProgress = 0;
    downloadMessage = "Starting download...";
    error = null;
    try {
      await downloadModel(modelId, (p: DownloadProgress) => {
        downloadProgress = p.progress;
        downloadMessage = p.message;
      });
      onmodelschange();
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      downloadingId = null;
    }
  }

  async function handleLoad(modelId: string) {
    loadingId = modelId;
    error = null;
    try {
      await loadModel(modelId);
      onmodelschange();
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loadingId = null;
    }
  }
</script>

{#if open}
  <div class="settings-backdrop" onclick={onclose} role="presentation"></div>
  <div class="settings-panel">
    <div class="settings-header">
      <h2>Settings</h2>
      <button class="close-btn" onclick={onclose}>&times;</button>
    </div>

    <div class="settings-content">
      <h3>Models</h3>
      <p class="settings-desc">
        Select a translation model. Larger models are more accurate but require
        more RAM and are slower.
      </p>

      {#if error}
        <div class="error-banner">{error}</div>
      {/if}

      {#each models as model}
        <div
          class="model-card"
          class:active={model.id === currentModelId}
        >
          <div class="model-info">
            <div class="model-name">
              {model.name}
              {#if model.id === currentModelId}
                <span class="badge active-badge">Active</span>
              {/if}
            </div>
            <div class="model-meta">
              {model.ramGb}GB RAM &middot; {model.description}
            </div>
          </div>

          <div class="model-actions">
            {#if downloadingId === model.id}
              <div class="progress-container">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    style="width: {downloadProgress * 100}%"
                  ></div>
                </div>
                <span class="progress-text">{downloadMessage}</span>
              </div>
            {:else if model.status === "not_downloaded"}
              <button
                class="btn btn-primary"
                onclick={() => handleDownload(model.id)}
                disabled={downloadingId !== null || loadingId !== null}
              >
                Download
              </button>
            {:else if model.status === "downloaded" && model.id !== currentModelId}
              <button
                class="btn btn-secondary"
                onclick={() => handleLoad(model.id)}
                disabled={loadingId !== null || downloadingId !== null}
              >
                {loadingId === model.id ? "Loading..." : "Load"}
              </button>
            {:else if model.status === "loading"}
              <span class="status-text">Loading...</span>
            {:else if model.status === "ready" && model.id !== currentModelId}
              <button
                class="btn btn-secondary"
                onclick={() => handleLoad(model.id)}
                disabled={loadingId !== null}
              >
                Switch to this
              </button>
            {:else if model.status === "error"}
              <div class="error-text">{model.error}</div>
              <button
                class="btn btn-primary"
                onclick={() => handleDownload(model.id)}
                disabled={downloadingId !== null}
              >
                Retry
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
{/if}

<style>
  .settings-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 100;
  }

  .settings-panel {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 420px;
    max-width: 90vw;
    background: var(--bg);
    border-left: 1px solid var(--border);
    z-index: 101;
    display: flex;
    flex-direction: column;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.4);
  }

  .settings-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
  }

  .settings-header h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 600;
  }

  .close-btn {
    background: none;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: var(--text-secondary);
    padding: 0 4px;
  }

  .settings-content {
    padding: 20px;
    overflow-y: auto;
    flex: 1;
  }

  .settings-content h3 {
    margin: 0 0 8px 0;
    font-size: 15px;
    font-weight: 600;
  }

  .settings-desc {
    margin: 0 0 16px 0;
    font-size: 13px;
    color: var(--text-secondary);
    line-height: 1.5;
  }

  .error-banner {
    padding: 10px 14px;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 8px;
    color: #ef4444;
    font-size: 13px;
    margin-bottom: 12px;
  }

  .model-card {
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 10px;
    background: var(--surface);
  }

  .model-card.active {
    border-color: var(--accent);
    background: rgba(99, 102, 241, 0.08);
  }

  .model-info {
    margin-bottom: 10px;
  }

  .model-name {
    font-weight: 600;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    font-weight: 500;
  }

  .active-badge {
    background: var(--accent);
    color: white;
  }

  .model-meta {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 4px;
  }

  .model-actions {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .btn {
    padding: 0.6rem 1rem;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    border: none;
    transition: background 0.15s;
    white-space: nowrap;
  }

  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .btn-primary {
    background: #ededed;
    color: #0a0a0b;
  }

  .btn-primary:hover:not(:disabled) {
    background: #fff;
  }

  .btn-secondary {
    background: rgba(255, 255, 255, 0.06);
    color: var(--text);
    border: 1px solid var(--border);
  }

  .btn-secondary:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
  }

  .progress-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .progress-bar {
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
  }

  .progress-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 3px;
    transition: width 0.3s;
  }

  .progress-text {
    font-size: 11px;
    color: var(--text-secondary);
  }

  .status-text {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .error-text {
    font-size: 12px;
    color: #ef4444;
  }
</style>
