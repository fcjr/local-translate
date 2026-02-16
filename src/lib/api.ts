import { pyInvoke } from "tauri-plugin-pytauri-api";
import { Channel } from "@tauri-apps/api/core";

export interface LanguageInfo {
  code: string;
  name: string;
}

export interface ModelInfo {
  id: string;
  name: string;
  repoId: string;
  ramGb: number;
  description: string;
  status: string;
  error: string | null;
}

export interface ModelStatusResponse {
  modelId: string;
  status: string;
  currentModelId: string | null;
  error: string | null;
}

export interface DownloadProgress {
  progress: number;
  message: string;
}

export async function listLanguages(): Promise<LanguageInfo[]> {
  return await pyInvoke<LanguageInfo[]>("list_languages");
}

export async function translate(
  text: string,
  sourceLang: string,
  targetLang: string
): Promise<string> {
  return await pyInvoke<string>("translate", {
    text,
    sourceLang,
    targetLang,
  });
}

export async function listModels(): Promise<ModelInfo[]> {
  return await pyInvoke<ModelInfo[]>("list_models");
}

export async function getModelStatus(
  modelId: string
): Promise<ModelStatusResponse> {
  return await pyInvoke<ModelStatusResponse>("get_model_status", { modelId });
}

export async function downloadModel(
  modelId: string,
  onProgress: (progress: DownloadProgress) => void
): Promise<string> {
  const channel = new Channel<DownloadProgress>();
  channel.onmessage = onProgress;
  return await pyInvoke<string>("download_model", {
    modelId,
    onProgress: channel,
  });
}

export async function loadModel(
  modelId: string
): Promise<ModelStatusResponse> {
  return await pyInvoke<ModelStatusResponse>("load_model", { modelId });
}

export async function switchModel(
  modelId: string
): Promise<ModelStatusResponse> {
  return await pyInvoke<ModelStatusResponse>("switch_model", { modelId });
}

// --- TTS ---

export interface TtsStatus {
  status: string;
  error: string | null;
}

export async function getTtsStatus(): Promise<TtsStatus> {
  return await pyInvoke<TtsStatus>("get_tts_status");
}

export async function downloadTtsModel(
  onProgress: (progress: DownloadProgress) => void
): Promise<string> {
  const channel = new Channel<DownloadProgress>();
  channel.onmessage = onProgress;
  return await pyInvoke<string>("download_tts_model", {
    onProgress: channel,
  });
}

export async function loadTtsModel(): Promise<TtsStatus> {
  return await pyInvoke<TtsStatus>("load_tts_model");
}

export async function synthesizeSpeech(
  text: string,
  language: string
): Promise<string> {
  return await pyInvoke<string>("synthesize_speech", { text, language });
}
