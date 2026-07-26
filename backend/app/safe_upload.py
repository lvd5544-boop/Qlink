"""Bounded, random-name upload handling with deterministic cleanup."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
from pathlib import Path
import tempfile
from typing import Callable
import zipfile

import fitz
from fastapi import HTTPException, UploadFile


ALLOWED_MIME = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".txt": {"text/plain", "application/octet-stream"},
}


def _limit(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _validate_magic(path: Path, extension: str) -> None:
    header = path.read_bytes()[:8]
    if extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise HTTPException(status_code=415, detail="文件内容与 PDF 格式不匹配")
    if extension == ".docx" and not header.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=415, detail="文件内容与 DOCX 格式不匹配")
    if extension == ".txt":
        sample = path.read_bytes()[:8192]
        if b"\x00" in sample:
            raise HTTPException(status_code=415, detail="TXT 文件包含无效二进制内容")
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=415, detail="TXT 文件必须使用 UTF-8 编码") from exc


def _validate_container_limits_sync(path: Path, extension: str) -> None:
    if extension == ".pdf":
        try:
            with fitz.open(path) as document:
                if document.page_count > _limit("UPLOAD_MAX_PAGES", 30):
                    raise HTTPException(status_code=413, detail="PDF 页数超过限制")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail="PDF 文件无法安全解析") from exc
    elif extension == ".docx":
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > _limit("UPLOAD_MAX_ARCHIVE_ENTRIES", 1000):
                    raise HTTPException(status_code=413, detail="DOCX 文件条目过多")
                total = sum(item.file_size for item in entries)
                if total > _limit("UPLOAD_MAX_UNCOMPRESSED_BYTES", 20 * 1024 * 1024):
                    raise HTTPException(status_code=413, detail="DOCX 解压后内容超过限制")
        except HTTPException:
            raise
        except (zipfile.BadZipFile, OSError) as exc:
            raise HTTPException(status_code=422, detail="DOCX 文件无法安全解析") from exc


def _file_worker(
    result_queue,
    operation: str,
    path_text: str,
    extension: str,
) -> None:
    path = Path(path_text)
    try:
        if operation == "validate":
            _validate_container_limits_sync(path, extension)
            result = None
        elif operation == "extract":
            if extension == ".pdf":
                from .resume_parser import extract_text_from_pdf

                result = extract_text_from_pdf(str(path))
            elif extension == ".docx":
                from .resume_parser import extract_text_from_docx

                result = extract_text_from_docx(str(path))
            else:
                result = path.read_text(encoding="utf-8")
        else:
            raise ValueError("unknown file operation")
        result_queue.put(("ok", result))
    except HTTPException as exc:
        result_queue.put(("http", exc.status_code, exc.detail))
    except Exception:
        result_queue.put(("error",))


async def _run_file_worker(
    operation: str,
    path: Path,
    extension: str,
    timeout_seconds: float,
):
    context = multiprocessing.get_context("spawn")
    result_queue = context.Queue(maxsize=1)
    process = context.Process(
        target=_file_worker,
        args=(result_queue, operation, str(path), extension),
        daemon=True,
    )
    process.start()
    try:
        message = await asyncio.wait_for(
            asyncio.to_thread(result_queue.get),
            timeout=max(0.1, timeout_seconds),
        )
    except asyncio.TimeoutError as exc:
        if process.is_alive():
            process.terminate()
            await asyncio.to_thread(process.join, 2)
        raise HTTPException(status_code=408, detail="文件解析超时") from exc
    finally:
        if process.is_alive():
            await asyncio.to_thread(process.join, 2)
        if process.is_alive():
            process.terminate()
            await asyncio.to_thread(process.join, 2)

    if process.exitcode != 0:
        raise HTTPException(status_code=422, detail="文件解析失败")
    result_queue.close()
    if message[0] == "http":
        raise HTTPException(status_code=message[1], detail=message[2])
    if message[0] != "ok":
        raise HTTPException(status_code=422, detail="文件解析失败")
    return message[1]


async def save_upload_safely(upload: UploadFile, directory: str) -> tuple[Path, str]:
    original_name = Path(upload.filename or "").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_MIME:
        raise HTTPException(status_code=415, detail="仅支持 PDF、DOCX、TXT 格式")
    content_type = (upload.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_MIME[extension]:
        raise HTTPException(status_code=415, detail="文件 MIME 类型与扩展名不匹配")

    target_dir = Path(directory)
    target_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = _limit("UPLOAD_MAX_BYTES", 5 * 1024 * 1024)
    fd, raw_path = tempfile.mkstemp(prefix="upload-", suffix=extension, dir=str(target_dir))
    path = Path(raw_path)
    size = 0
    try:
        with os.fdopen(fd, "wb") as destination:
            while True:
                chunk = await upload.read(64 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(status_code=413, detail="上传文件超过大小限制")
                destination.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="上传文件为空")
        _validate_magic(path, extension)
        if extension in {".pdf", ".docx"}:
            await _run_file_worker(
                "validate",
                path,
                extension,
                float(os.getenv("UPLOAD_PARSE_TIMEOUT_SECONDS", "10")),
            )
        return path, extension
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


async def extract_text_bounded(
    path: Path,
    extension: str,
    pdf_extractor: Callable[[str], str],
    docx_extractor: Callable[[str], str],
) -> str:
    try:
        # 文件解析必须运行在可终止的独立进程中；wait_for(to_thread)
        # 只能停止等待，不能终止恶意解析线程。
        text = await _run_file_worker(
            "extract",
            path,
            extension,
            float(os.getenv("UPLOAD_PARSE_TIMEOUT_SECONDS", "10")),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="文件解析失败") from exc

    max_chars = _limit("UPLOAD_MAX_TEXT_CHARS", 100_000)
    if len(text) > max_chars:
        raise HTTPException(status_code=413, detail="解析后的文本超过长度限制")
    if not text.strip():
        raise HTTPException(status_code=422, detail="文件中未提取到有效文本")
    return text


async def call_parser_bounded(parser: Callable[[str], object], text: str):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(parser, text),
            timeout=float(os.getenv("MODEL_PARSE_TIMEOUT_SECONDS", "45")),
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(status_code=504, detail="智能解析超时，请稍后重试") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="智能解析失败，请稍后重试") from exc
