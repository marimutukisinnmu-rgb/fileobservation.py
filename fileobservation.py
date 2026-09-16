#!/usr/bin/env python3
"""Real-time file system observation CLI.

CLI:
    python fileobservation.py -f <folder>
    python fileobservation.py -f <folder> -l <log-file>
    python fileobservation.py -g -f <folder>
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except ImportError:
    print("watchdog が必要です。: python -m pip install watchdog", file=sys.stderr)
    raise SystemExit(1)


class FileObserverHandler(FileSystemEventHandler):
    """Print every received event immediately and optionally buffer log-file writes."""

    def __init__(self, log_path: Path | None = None) -> None:
        super().__init__()
        self.log_path = log_path
        self._log_buffer: list[str] = []
        self._log_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._log_thread: threading.Thread | None = None

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

    def _emit(self, event_type: str, src_path: str, dest_path: str | None = None) -> None:
        if dest_path is None:
            line = f"[{self._timestamp()}] {event_type:<8} {src_path}"
        else:
            line = f"[{self._timestamp()}] {event_type:<8} {src_path} -> {dest_path}"

        # CLI output is intentionally immediate: no debouncing/coalescing.
        print(line, flush=True)

        if self.log_path is not None:
            with self._log_lock:
                self._log_buffer.append(line)

    def on_created(self, event):
        self._emit("CREATED", event.src_path)

    def on_modified(self, event):
        self._emit("MODIFIED", event.src_path)

    def on_deleted(self, event):
        self._emit("DELETED", event.src_path)

    def on_moved(self, event):
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
        description="リアルタイムでフォルダーのファイル変更を監視します。",
    )
    parser.add_argument(
        "-f",
        "--folder",
        required=False,
        help="監視するフォルダーのパス",
    )
    parser.add_argument(
        "-l",
        "--log",
        "-log",
        dest="log",
        help="ログを書き込むTXTファイルのパス（最大約1秒遅延）",
    )
    parser.add_argument(
        "-g",
        "--gui",
        action="store_true",
        help="GUIモード（現段階ではCLI監視にフォルダー選択UIを追加するための入口）",
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
    observer.schedule(handler, str(folder), recursive=True)
    observer.start()

    print(f"監視開始: {folder}", flush=True)
    if log_path is not None:
        print(f"ログ: {log_path}（約1秒ごとに書き込み）", flush=True)
    print("終了するには Ctrl+C", flush=True)

    try:
        while True:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n監視停止中...", flush=True)
    finally:
        observer.stop()
        observer.join()
        handler.close()
        print("監視を終了しました。", flush=True)

    return 0


def run_gui(folder: Path | None, log_path: Path | None) -> int:
    # Keep -g usable even before the full GUI is implemented.
    # A Tkinter UI can be layered on this same observer handler later.
    if folder is None:
        print("-g は現段階では -f で監視フォルダーを指定してください。", file=sys.stderr)
        return 2
    return run_cli(folder, log_path)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.folder is None:
        parser.error("監視フォルダーを -f / --folder で指定してください")

    folder = Path(os.path.expandvars(os.path.expanduser(args.folder))).resolve()
    log_path = None
    if args.log:
        log_path = Path(os.path.expandvars(os.path.expanduser(args.log))).resolve()

    if args.gui:
        return run_gui(folder, log_path)
    return run_cli(folder, log_path)


if __name__ == "__main__":
    raise SystemExit(main())
