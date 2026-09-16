#!/usr/bin/env python3
"""Real-time file system observation CLI.

CLI:
    python fileobservation.py -f <folder>
    python fileobservation.py -f <folder> -l <log-file>

The CLI prints every file event immediately. Log-file writes are buffered
and flushed about once per second so disk I/O does not block event handling.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    print("watchdog が必要です。: python -m pip install watchdog", file=sys.stderr)
    raise SystemExit(1)


class FileObserverHandler(FileSystemEventHandler):
    """Handle every file event without debouncing or coalescing."""

    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self.log_path = log_path
        self._log_buffer: list[str] = []
        self._log_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._log_thread: threading.Thread | None = None

        # If the log is inside the watched folder, writing the log would
        # otherwise generate another event and create an endless feedback loop.
        self._log_path_resolved = (
            log_path.resolve(strict=False) if log_path is not None else None
        )

        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._log_thread = threading.Thread(
                target=self._flush_loop,
                name="fileobservation-log-flusher",
                daemon=True,
            )
            self._log_thread.start()

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _is_log_file(self, path: str) -> bool:
        if self._log_path_resolved is None:
            return False
        try:
            return Path(path).resolve(strict=False) == self._log_path_resolved
        except OSError:
            return False

    def _emit(
        self,
        event_type: str,
        src_path: str,
        dest_path: str | None = None,
    ) -> None:
        if self._is_log_file(src_path):
            return
        if dest_path is not None and self._is_log_file(dest_path):
            return

        if dest_path is None:
            line = f"[{self._timestamp()}] {event_type:<8} {src_path}"
        else:
            line = f"[{self._timestamp()}] {event_type:<8} {src_path} -> {dest_path}"

        # CLI output is deliberately immediate. Every event is printed;
        # there is no debouncing, throttling, or coalescing.
        print(line, flush=True)

        if self.log_path is not None:
            with self._log_lock:
                self._log_buffer.append(line)

    @staticmethod
    def _is_directory_event(event: Any) -> bool:
        return bool(getattr(event, "is_directory", False))

    def on_created(self, event: Any) -> None:
        if not self._is_directory_event(event):
            self._emit("CREATED", event.src_path)

    def on_modified(self, event: Any) -> None:
        if not self._is_directory_event(event):
            self._emit("MODIFIED", event.src_path)

    def on_deleted(self, event: Any) -> None:
        if not self._is_directory_event(event):
            self._emit("DELETED", event.src_path)

    def on_moved(self, event: Any) -> None:
        if not self._is_directory_event(event):
            self._emit("MOVED", event.src_path, event.dest_path)

    def _flush_loop(self) -> None:
        while not self._stop_event.wait(1.0):
            self.flush_log()
        self.flush_log()

    def flush_log(self) -> None:
        if self.log_path is None:
            return

        with self._log_lock:
            if not self._log_buffer:
                return
            lines = self._log_buffer
            self._log_buffer = []

        try:
            with self.log_path.open("a", encoding="utf-8", newline="") as log_file:
                log_file.write("\n".join(lines) + "\n")
        except OSError as exc:
            print(f"[LOG ERROR] {exc}", file=sys.stderr, flush=True)
            with self._log_lock:
                self._log_buffer[0:0] = lines

    def close(self) -> None:
        self._stop_event.set()
        if self._log_thread is not None:
            self._log_thread.join(timeout=2.0)
        self.flush_log()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fileobservation.py",
        description="リアルタイムでフォルダー内のファイル変更を監視します。",
    )
    parser.add_argument(
        "-f",
        "--folder",
        required=True,
        help="監視するフォルダーのパス",
    )
    parser.add_argument(
        "-l",
        "--log",
        "-log",
        dest="log",
        help="ログを書き込むTXTファイルのパス（約1秒ごとに書き込み）",
    )
    parser.add_argument(
        "-g",
        "--gui",
        action="store_true",
        help="GUIモード（未実装）",
    )
    return parser


def run_cli(folder: Path, log_path: Path | None) -> int:
    if not folder.exists():
        print(f"エラー: フォルダーが存在しません: {folder}", file=sys.stderr)
        return 2
    if not folder.is_dir():
        print(f"エラー: フォルダーではありません: {folder}", file=sys.stderr)
        return 2

    handler = FileObserverHandler(log_path)
    observer = Observer()

    try:
        observer.schedule(handler, str(folder), recursive=True)
        observer.start()
    except OSError as exc:
        handler.close()
        print(f"エラー: 監視を開始できませんでした: {exc}", file=sys.stderr)
        return 1

    print(f"監視開始: {folder}", flush=True)
    print("サブフォルダーも監視: ON", flush=True)
    if log_path is not None:
        print(f"ログ: {log_path}（約1秒ごとに書き込み）", flush=True)
    print("終了するには Ctrl+C", flush=True)

    try:
        while observer.is_alive():
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n監視停止中...", flush=True)
    finally:
        observer.stop()
        observer.join()
        handler.close()
        print("監視を終了しました。", flush=True)

    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # GUI is intentionally left for a later implementation. Keeping the
    # switch recognized now makes the command-line interface forward-compatible.
    if args.gui:
        print("GUIモードはまだ実装されていません。", file=sys.stderr)
        return 2

    folder = Path(os.path.expandvars(os.path.expanduser(args.folder))).resolve()
    log_path = None
    if args.log:
        log_path = Path(os.path.expandvars(os.path.expanduser(args.log))).resolve()

    return run_cli(folder, log_path)


if __name__ == "__main__":
    raise SystemExit(main())
