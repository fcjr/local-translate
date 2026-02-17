from __future__ import annotations

import anyio
from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer
from pytauri import Commands
from pytauri.ipc import JavaScriptChannelId, WebviewWindow

from local_translate.languages import SUPPORTED_LANGUAGES
from local_translate.model_manager import AVAILABLE_MODELS, ModelManager, ModelStatus
from local_translate.tts_manager import TtsManager, TtsStatus

commands: Commands = Commands()


def _to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


class CamelModel(BaseModel):
    """Base model that serializes to camelCase.

    pytauri calls model_dump_json() without by_alias=True.
    A model_serializer is used instead of overriding model_dump_json
    because it is respected during nested serialization (e.g. inside RootModel).
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    @model_serializer(mode="wrap")
    def _serialize_camel(self, handler: Any) -> dict[str, Any]:
        return {_to_camel(k): v for k, v in handler(self).items()}


# --- Request models ---


class TranslateRequest(CamelModel):
    text: str
    source_lang: str
    target_lang: str


class ModelIdRequest(CamelModel):
    model_id: str


class DownloadProgress(CamelModel):
    progress: float
    message: str


class DownloadModelRequest(CamelModel):
    model_id: str
    on_progress: JavaScriptChannelId[DownloadProgress]


class SynthesizeSpeechRequest(CamelModel):
    text: str
    language: str


class TtsStatusResponse(CamelModel):
    status: str
    error: str | None = None


class DownloadTtsModelRequest(CamelModel):
    on_progress: JavaScriptChannelId[DownloadProgress]


# --- Response models ---


class LanguageInfo(CamelModel):
    code: str
    name: str


class ModelInfo(CamelModel):
    id: str
    name: str
    repo_id: str
    ram_gb: int
    description: str
    status: str
    error: str | None = None


class ModelStatusResponse(CamelModel):
    model_id: str
    status: str
    current_model_id: str | None = None
    error: str | None = None


# --- Commands ---


@commands.command()
async def translate(body: TranslateRequest) -> str:
    manager = ModelManager()
    result = await anyio.to_thread.run_sync(
        lambda: manager.translate(body.text, body.source_lang, body.target_lang)
    )
    return result


@commands.command()
async def list_languages() -> list[LanguageInfo]:
    return [
        LanguageInfo(code=code, name=name)
        for code, name in sorted(SUPPORTED_LANGUAGES.items(), key=lambda x: x[1])
    ]


@commands.command()
async def list_models() -> list[ModelInfo]:
    manager = ModelManager()
    result = []
    for model_id, info in AVAILABLE_MODELS.items():
        status = manager.get_status(model_id)
        error = manager.get_error(model_id)
        result.append(
            ModelInfo(
                id=model_id,
                name=str(info["name"]),
                repo_id=str(info["repo_id"]),
                ram_gb=int(info["ram_gb"]),
                description=str(info["description"]),
                status=status.value,
                error=error,
            )
        )
    return result


@commands.command()
async def get_model_status(body: ModelIdRequest) -> ModelStatusResponse:
    manager = ModelManager()
    status = manager.get_status(body.model_id)
    error = manager.get_error(body.model_id)
    return ModelStatusResponse(
        model_id=body.model_id,
        status=status.value,
        current_model_id=manager.get_current_model_id(),
        error=error,
    )


@commands.command()
async def download_model(
    body: DownloadModelRequest, webview_window: WebviewWindow
) -> str:
    manager = ModelManager()
    channel = body.on_progress.channel_on(webview_window.as_ref_webview())

    def progress_callback(progress: float, message: str) -> None:
        channel.send_model(DownloadProgress(progress=progress, message=message))

    await anyio.to_thread.run_sync(
        lambda: manager.download_model(body.model_id, progress_callback)
    )
    return "ok"


@commands.command()
async def load_model(body: ModelIdRequest) -> ModelStatusResponse:
    manager = ModelManager()
    await anyio.to_thread.run_sync(lambda: manager.load_model(body.model_id))
    status = manager.get_status(body.model_id)
    return ModelStatusResponse(
        model_id=body.model_id,
        status=status.value,
        current_model_id=manager.get_current_model_id(),
    )


@commands.command()
async def delete_model(body: ModelIdRequest) -> ModelStatusResponse:
    manager = ModelManager()
    await anyio.to_thread.run_sync(lambda: manager.delete_model(body.model_id))
    status = manager.get_status(body.model_id)
    return ModelStatusResponse(
        model_id=body.model_id,
        status=status.value,
        current_model_id=manager.get_current_model_id(),
    )


@commands.command()
async def switch_model(body: ModelIdRequest) -> ModelStatusResponse:
    manager = ModelManager()
    if manager.get_status(body.model_id) == ModelStatus.NOT_DOWNLOADED:
        raise RuntimeError(f"Model {body.model_id} is not downloaded")
    await anyio.to_thread.run_sync(lambda: manager.load_model(body.model_id))
    status = manager.get_status(body.model_id)
    return ModelStatusResponse(
        model_id=body.model_id,
        status=status.value,
        current_model_id=manager.get_current_model_id(),
    )


# --- TTS Commands ---


@commands.command()
async def get_tts_status() -> TtsStatusResponse:
    tts = TtsManager()
    return TtsStatusResponse(
        status=tts.get_status().value,
        error=tts.get_error(),
    )


@commands.command()
async def download_tts_model(
    body: DownloadTtsModelRequest, webview_window: WebviewWindow
) -> str:
    tts = TtsManager()
    channel = body.on_progress.channel_on(webview_window.as_ref_webview())

    def progress_callback(progress: float, message: str) -> None:
        channel.send_model(DownloadProgress(progress=progress, message=message))

    await anyio.to_thread.run_sync(
        lambda: tts.download_model(progress_callback)
    )
    return "ok"


@commands.command()
async def load_tts_model() -> TtsStatusResponse:
    tts = TtsManager()
    await anyio.to_thread.run_sync(lambda: tts.load_model())
    return TtsStatusResponse(
        status=tts.get_status().value,
        error=tts.get_error(),
    )


@commands.command()
async def synthesize_speech(body: SynthesizeSpeechRequest) -> str:
    tts = TtsManager()
    result = await anyio.to_thread.run_sync(
        lambda: tts.synthesize(body.text, body.language)
    )
    return result
