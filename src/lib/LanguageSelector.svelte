<script lang="ts">
  import type { LanguageInfo } from "./api";

  interface Props {
    languages: LanguageInfo[];
    value: string;
    favorites: string[];
    recents: string[];
    onchange: (code: string) => void;
    ontogglefavorite: (code: string) => void;
  }

  let { languages, value, favorites, recents, onchange, ontogglefavorite }: Props = $props();

  let open = $state(false);
  let search = $state("");
  let containerEl: HTMLDivElement | undefined = $state();
  let searchInputEl: HTMLInputElement | undefined = $state();

  let selectedName = $derived(
    languages.find((l) => l.code === value)?.name ?? value
  );

  function langsByCode(codes: string[]): LanguageInfo[] {
    return codes
      .map((c) => languages.find((l) => l.code === c))
      .filter((l): l is LanguageInfo => l !== undefined);
  }

  let favoriteLangs = $derived(langsByCode(favorites));
  let recentLangs = $derived(
    langsByCode(recents.filter((c) => !favorites.includes(c)))
  );

  let allLangs = $derived(
    languages.filter((l) => !favorites.includes(l.code))
  );

  let filteredAll = $derived(
    search.trim()
      ? allLangs.filter((l) =>
          l.name.toLowerCase().includes(search.trim().toLowerCase()) ||
          l.code.toLowerCase().includes(search.trim().toLowerCase())
        )
      : allLangs
  );

  let filteredFavorites = $derived(
    search.trim()
      ? favoriteLangs.filter((l) =>
          l.name.toLowerCase().includes(search.trim().toLowerCase()) ||
          l.code.toLowerCase().includes(search.trim().toLowerCase())
        )
      : favoriteLangs
  );

  let filteredRecents = $derived(
    search.trim()
      ? recentLangs.filter((l) =>
          l.name.toLowerCase().includes(search.trim().toLowerCase()) ||
          l.code.toLowerCase().includes(search.trim().toLowerCase())
        )
      : recentLangs
  );

  function toggle() {
    open = !open;
    search = "";
    if (open) {
      requestAnimationFrame(() => searchInputEl?.focus());
    }
  }

  function select(code: string) {
    onchange(code);
    open = false;
    search = "";
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Escape") {
      open = false;
      search = "";
    }
  }

  function handleClickOutside(e: MouseEvent) {
    if (containerEl && !containerEl.contains(e.target as Node)) {
      open = false;
      search = "";
    }
  }

  function isFavorite(code: string): boolean {
    return favorites.includes(code);
  }

  $effect(() => {
    if (open) {
      document.addEventListener("click", handleClickOutside, true);
      document.addEventListener("keydown", handleKeydown);
    }
    return () => {
      document.removeEventListener("click", handleClickOutside, true);
      document.removeEventListener("keydown", handleKeydown);
    };
  });
</script>

<div class="lang-selector" bind:this={containerEl}>
  <button class="trigger" onclick={toggle} type="button">
    <span class="trigger-text">{selectedName}</span>
    <svg class="trigger-chevron" class:open width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </button>

  {#if open}
    <div class="dropdown">
      <div class="search-box">
        <input
          bind:this={searchInputEl}
          bind:value={search}
          type="text"
          class="search-input"
          placeholder="Search languages..."
        />
      </div>

      <div class="dropdown-scroll">
        {#if filteredFavorites.length > 0}
          <div class="section">
            <div class="section-label">Favorites</div>
            {#each filteredFavorites as lang}
              <div class="lang-row" class:selected={lang.code === value}>
                <button class="lang-btn" onclick={() => select(lang.code)} type="button">
                  {lang.name}
                </button>
                <button
                  class="star-btn starred"
                  onclick={(e) => { e.stopPropagation(); ontogglefavorite(lang.code); }}
                  type="button"
                  title="Remove from favorites"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                  </svg>
                </button>
              </div>
            {/each}
          </div>
        {/if}

        {#if filteredRecents.length > 0}
          <div class="section">
            <div class="section-label">Recent</div>
            {#each filteredRecents as lang}
              <div class="lang-row" class:selected={lang.code === value}>
                <button class="lang-btn" onclick={() => select(lang.code)} type="button">
                  {lang.name}
                </button>
                <button
                  class="star-btn" class:starred={isFavorite(lang.code)}
                  onclick={(e) => { e.stopPropagation(); ontogglefavorite(lang.code); }}
                  type="button"
                  title="Add to favorites"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                  </svg>
                </button>
              </div>
            {/each}
          </div>
        {/if}

        <div class="section">
          {#if filteredFavorites.length > 0 || filteredRecents.length > 0}
            <div class="section-label">All Languages</div>
          {/if}
          {#each filteredAll as lang}
            <div class="lang-row" class:selected={lang.code === value}>
              <button class="lang-btn" onclick={() => select(lang.code)} type="button">
                {lang.name}
              </button>
              <button
                class="star-btn" class:starred={isFavorite(lang.code)}
                onclick={(e) => { e.stopPropagation(); ontogglefavorite(lang.code); }}
                type="button"
                title={isFavorite(lang.code) ? "Remove from favorites" : "Add to favorites"}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill={isFavorite(lang.code) ? "currentColor" : "none"} stroke="currentColor" stroke-width="1.5">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
                </svg>
              </button>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .lang-selector {
    position: relative;
  }

  .trigger {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0.5rem 0.75rem;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.03);
    color: #ededed;
    font-size: 0.875rem;
    font-family: inherit;
    cursor: pointer;
    min-width: 160px;
    transition: border-color 0.15s;
  }

  .trigger:hover {
    border-color: rgba(255, 255, 255, 0.15);
  }

  .trigger-text {
    flex: 1;
    text-align: left;
  }

  .trigger-chevron {
    flex-shrink: 0;
    color: #888;
    transition: transform 0.15s;
  }

  .trigger-chevron.open {
    transform: rotate(180deg);
  }

  .dropdown {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    width: 260px;
    max-height: 360px;
    background: #1c1c1e;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
    z-index: 100;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .search-box {
    padding: 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  }

  .search-input {
    width: 100%;
    padding: 7px 10px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.04);
    color: #ededed;
    font-size: 0.8125rem;
    font-family: inherit;
    outline: none;
    transition: border-color 0.15s;
  }

  .search-input:focus {
    border-color: #6366f1;
  }

  .search-input::placeholder {
    color: #555;
  }

  .dropdown-scroll {
    overflow-y: auto;
    flex: 1;
  }

  .section {
    padding: 4px 0;
  }

  .section + .section {
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }

  .section-label {
    padding: 6px 12px 4px;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #555;
  }

  .lang-row {
    display: flex;
    align-items: center;
    padding: 0 4px;
  }

  .lang-row.selected {
    background: rgba(99, 102, 241, 0.12);
  }

  .lang-btn {
    flex: 1;
    text-align: left;
    padding: 6px 8px;
    background: none;
    border: none;
    color: #ededed;
    font-size: 0.8125rem;
    font-family: inherit;
    cursor: pointer;
    border-radius: 4px;
  }

  .lang-btn:hover {
    background: rgba(255, 255, 255, 0.06);
  }

  .star-btn {
    flex-shrink: 0;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: #444;
    cursor: pointer;
    border-radius: 4px;
    transition: color 0.15s;
  }

  .star-btn:hover {
    color: #f59e0b;
  }

  .star-btn.starred {
    color: #f59e0b;
  }
</style>
