# 作業記録

## 2026-09-18 — 音声保存

- `yt-dlp` で `bestaudio` のみを `~/Music/ytplayer/` へ保存する処理を追加。
- ファイル名にYouTube動画IDを保持し、同一IDの再ダウンロードを回避。
- 再生は保存済みローカル音声を優先し、保存失敗時はストリーミングを使う。
- `YTPLAYER_MUSIC_DIR` で保存先を上書き可能にした。
- `PYTHONPATH=src python -m pytest -q` を実行し、10件成功。
