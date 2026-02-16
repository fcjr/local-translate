from __future__ import annotations

import anyio
from pydantic import BaseModel, ConfigDict, RootModel
from pytauri import Commands
from pytauri.ipc import JavaScriptChannelId, WebviewWindow

from local_translate.languages import SUPPORTED_LANGUAGES
from local_translate.model_manager import AVAILABLE_MODELS, ModelManager, ModelStatus

commands: Commands = Commands()


def _camel_config() -> ConfigDict:
    return ConfigDict(populate_by_name=True, alias_generator=lambda s: _to_camel(s))


def _to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(w.capitalize() for w in parts[1:])


# --- Request models ---


class TranslateRequest(BaseModel):
    model_config = _camel_config()
    text: str
    source_lang: str
    target_lang: str


class ModelIdRequest(BaseModel):
    model_config = _camel_config()
    model_id: str


class DownloadProgress(BaseModel):
    model_config = _camel_config()
    progress: float
    message: str


class DownloadModelRequest(BaseModel):
    model_config = _camel_config()
    model_id: str
    on_progress: JavaScriptChannelId[DownloadProgress]


# --- Response models ---


class LanguageInfo(BaseModel):
    model_config = _camel_config()
    code: str
    name: str


class ModelInfo(BaseModel):
    model_config = _camel_config()
    id: str
    name: str
    repo_id: str
    ram_gb: int
    description: str
    status: str
    error: str | None = None


class ModelStatusResponse(BaseModel):
    model_config = _camel_config()
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
