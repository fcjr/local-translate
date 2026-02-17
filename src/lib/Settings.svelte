<script lang="ts">
  import type { ModelInfo } from "./api";
  import { loadModel, deleteModel } from "./api";
  import DownloadSimpleIcon from "phosphor-svelte/lib/DownloadSimpleIcon";
  import PowerIcon from "phosphor-svelte/lib/PowerIcon";
  import TrashIcon from "phosphor-svelte/lib/TrashIcon";
  import CheckIcon from "phosphor-svelte/lib/CheckIcon";
  import CheckCircleIcon from "phosphor-svelte/lib/CheckCircleIcon";
  import XIcon from "phosphor-svelte/lib/XIcon";
  import ArrowCounterClockwiseIcon from "phosphor-svelte/lib/ArrowCounterClockwiseIcon";

  interface Props {
    open: boolean;
    models: ModelInfo[];
    currentModelId: string | null;
    downloadingId: string | null;
    downloadProgress: number;
    downloadMessage: string;
    downloadError: string | null;
    updateAvailable: { version: string; install: () => Promise<void> } | null;
    updateInstalling: boolean;
    onclose: () => void;
    onmodelschange: () => void;
    ondownload: (modelId: string) => void;
    oncheckupdate: () => void;
  }

  let { open, models, currentModelId, downloadingId, downloadProgress, downloadMessage, downloadError, updateAvailable, updateInstalling, onclose, onmodelschange, ondownload, oncheckupdate }: Props =
    $props();

  let updateChecking = $state(false);

  async function handleCheckUpdate() {
    updateChecking = true;
    oncheckupdate();
    // Give it a moment so the user sees feedback
    setTimeout(() => { updateChecking = false; }, 2000);
  }

  let loadingId: string | null = $state(null);
  let deletingId: string | null = $state(null);
  let confirmingDeleteId: string | null = $state(null);
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

  function handleDeleteClick(modelId: string) {
    if (confirmingDeleteId === modelId) {
      doDelete(modelId);
    } else {
      confirmingDeleteId = modelId;
    }
  }

  function cancelDelete() {
    confirmingDeleteId = null;
  }

  async function doDelete(modelId: string) {
    confirmingDeleteId = null;
    deletingId = modelId;
    error = null;
    try {
      await deleteModel(modelId);
      onmodelschange();
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      deletingId = null;
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

      {#if error || downloadError}
        <div class="error-banner">{error || downloadError}</div>
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
            {:else if model.status === "downloading"}
              <span class="status-text">Downloading...</span>
            {:else if model.status === "not_downloaded"}
              <button
                class="icon-btn"
                onclick={() => ondownload(model.id)}
                disabled={downloadingId !== null || loadingId !== null || deletingId !== null}
                title="Download"
              >
                <DownloadSimpleIcon size={16} />
              </button>
            {:else if (model.status === "downloaded" || model.status === "ready") && model.id !== currentModelId}
              {#if confirmingDeleteId === model.id}
                <span class="confirm-text">Delete?</span>
                <button
                  class="icon-btn icon-btn-danger"
                  onclick={() => handleDeleteClick(model.id)}
                  title="Confirm delete"
                >
                  <CheckIcon size={16} />
                </button>
                <button
                  class="icon-btn"
                  onclick={cancelDelete}
                  title="Cancel"
                >
                  <XIcon size={16} />
                </button>
              {:else if deletingId === model.id}
                <div class="action-spinner"></div>
              {:else if loadingId === model.id}
                <div class="action-spinner"></div>
              {:else}
                <button
                  class="icon-btn icon-btn-primary"
                  onclick={() => handleLoad(model.id)}
                  disabled={loadingId !== null || deletingId !== null}
                  title={model.status === "ready" ? "Switch to this model" : "Load model"}
                >
                  <PowerIcon size={16} weight="fill" />
                </button>
                <button
                  class="icon-btn icon-btn-danger"
                  onclick={() => handleDeleteClick(model.id)}
                  disabled={loadingId !== null || deletingId !== null}
                  title="Delete model"
                >
                  <TrashIcon size={16} />
                </button>
              {/if}
            {:else if model.id === currentModelId}
              <span class="active-indicator">
                <CheckCircleIcon size={16} weight="fill" />
                In use
              </span>
            {:else if model.status === "loading"}
              <div class="action-spinner"></div>
            {:else if model.status === "error"}
              <div class="error-text">{model.error}</div>
              <button
                class="icon-btn"
                onclick={() => ondownload(model.id)}
                disabled={downloadingId !== null}
                title="Retry download"
              >
                <ArrowCounterClockwiseIcon size={16} />
              </button>
            {/if}
          </div>
        </div>
      {/each}

      <h3 class="section-title">Updates</h3>
      {#if updateAvailable}
        <div class="update-card">
          <div class="update-info">
            <span class="update-version">v{updateAvailable.version} available</span>
          </div>
          <button
            class="update-btn"
            onclick={updateAvailable.install}
            disabled={updateInstalling}
          >
            {#if updateInstalling}
              Installing...
            {:else}
              Install & Restart
            {/if}
          </button>
        </div>
      {:else}
        <div class="update-card">
          <div class="update-info">
            <span class="update-status">
              {#if updateChecking}
                Checking...
              {:else}
                No updates available
              {/if}
            </span>
          </div>
          <button
            class="update-btn update-btn-secondary"
            onclick={handleCheckUpdate}
            disabled={updateChecking}
          >
            Check Now
          </button>
        </div>
      {/if}
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
    gap: 6px;
    min-height: 32px;
  }

  .icon-btn {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: color 0.15s, background 0.15s, border-color 0.15s;
    flex-shrink: 0;
  }

  .icon-btn:hover:not(:disabled) {
    color: var(--text);
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.15);
  }

  .icon-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .icon-btn-primary {
    color: #ededed;
    background: rgba(99, 102, 241, 0.15);
    border-color: rgba(99, 102, 241, 0.3);
  }

  .icon-btn-primary:hover:not(:disabled) {
    background: rgba(99, 102, 241, 0.25);
    border-color: rgba(99, 102, 241, 0.4);
    color: #fff;
  }

  .icon-btn-danger {
    color: #ef4444;
    border-color: rgba(239, 68, 68, 0.2);
    background: rgba(239, 68, 68, 0.08);
  }

  .icon-btn-danger:hover:not(:disabled) {
    background: rgba(239, 68, 68, 0.18);
    border-color: rgba(239, 68, 68, 0.35);
  }

  .action-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255, 255, 255, 0.08);
    border-top-color: var(--accent);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
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

  .active-indicator {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 13px;
    color: #22c55e;
    font-weight: 500;
  }

  .confirm-text {
    font-size: 13px;
    color: #ef4444;
    font-weight: 500;
  }

  .error-text {
    font-size: 12px;
    color: #ef4444;
  }

  .section-title {
    margin: 24px 0 12px 0;
    font-size: 15px;
    font-weight: 600;
  }

  .update-card {
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 14px;
    background: var(--surface);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }

  .update-info {
    flex: 1;
    min-width: 0;
  }

  .update-version {
    font-weight: 600;
    font-size: 14px;
    color: #818cf8;
  }

  .update-status {
    font-size: 13px;
    color: var(--text-secondary);
  }

  .update-btn {
    padding: 6px 14px;
    border-radius: 8px;
    border: 1px solid rgba(99, 102, 241, 0.3);
    background: rgba(99, 102, 241, 0.15);
    color: #818cf8;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
    transition: background 0.15s, border-color 0.15s;
  }

  .update-btn:hover:not(:disabled) {
    background: rgba(99, 102, 241, 0.25);
    border-color: rgba(99, 102, 241, 0.5);
  }

  .update-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .update-btn-secondary {
    background: rgba(255, 255, 255, 0.06);
    border-color: var(--border);
    color: var(--text-secondary);
  }

  .update-btn-secondary:hover:not(:disabled) {
    background: rgba(255, 255, 255, 0.1);
    border-color: rgba(255, 255, 255, 0.15);
    color: var(--text);
  }
</style>
