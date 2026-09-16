# fileobservation.py

リアルタイムでフォルダー内のファイル変更を監視するPythonツールです。

## 特徴

- ファイルの作成・変更・削除・移動をリアルタイムに検知
- CLIでイベントを即時表示
- ログファイルへの出力に対応
- GUIモードを予定
- MIT License

## 使い方

```text
fileobservation.py -f "監視するフォルダー"
```

ログファイルを指定する場合：

```text
fileobservation.py -f "監視するフォルダー" -l "log.txt"
```

GUIモード：

```text
fileobservation.py -g -f "監視するフォルダー"
```

## 出力について

CLIへのイベント表示はリアルタイムで行います。

ログファイルへの書き込みは、CLI表示やファイル監視処理をできるだけ妨げないよう、多少の遅延を許容してまとめて処理する設計です。

## 開発予定

- [ ] CLI監視機能の強化
- [ ] GUIの実装
- [ ] ログ出力機能の強化
- [ ] 設定機能
- [ ] テストの追加

## License

MIT License

Copyright (c) 2026 marimutukisinnmu-rgb
