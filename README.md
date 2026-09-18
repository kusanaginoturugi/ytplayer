# ytplayer

YouTube を `yt-dlp` で検索し、`mpv` で再生するメタデータ中心の TUI 音楽プレーヤー。

## 必要なもの

- Python 3.11+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（`pip install -e .` で導入される）
- `mpv`（PATH 上に必要）

Arch Linux なら、OS 管理の Python に `pip install` はしない。必要なら以下を pacman で入れる。

```sh
sudo pacman -S mpv python-yt-dlp
```

## 起動

リポジトリを開いた状態なら、インストールなしで起動できる。

```sh
./ytplayer
```

開発用に Python パッケージとして入れたい場合だけ、仮想環境を使う。

```sh
python -m venv .venv
.venv/bin/pip install -e .
.venv/bin/ytplayer
```

初回起動時に検索語を入力する。履歴DBは `~/.local/share/ytplayer/history.sqlite3` に作られる。
保存先を変える場合は `YTPLAYER_DATA_DIR=/path/to/data ./ytplayer` を使う。

曲を再生すると、音声だけを `~/Music/ytplayer/` へ保存する。YouTube動画IDを含むファイル名で管理するため、同じ曲は再ダウンロードしない。保存先は `YTPLAYER_MUSIC_DIR=/path/to/music ./ytplayer` で変更できる。ダウンロード元の利用規約と権利条件を守って使うこと。

## 年齢制限付き動画

年齢制限付き動画は、ログイン済みブラウザの Cookie なしには YouTube 側が再生を許可しない。通常の検索では、その動画だけを自動で飛ばして他の候補を続けて表示する。

自分のブラウザで YouTube にログイン済みなら、起動時にだけ Cookie を渡せる。Cookie の内容はこのプロジェクトや履歴DBには保存しない。

```sh
YTPLAYER_COOKIES_FROM_BROWSER=firefox ./ytplayer
# Chromium の場合
YTPLAYER_COOKIES_FROM_BROWSER=chromium ./ytplayer
```

特定プロファイルは `firefox:プロファイル名またはパス` の形で指定できる。ブラウザを完全に終了してから実行すると、Cookie DB のロックを避けやすい。

## 操作

| key | action |
| --- | --- |
| `s` | YouTube を検索し、候補一覧から選ぶ（再生中なら次曲として予約） |
| `m` | 現在曲のメタデータから次曲を選ぶ画面を開く |
| `↑` / `↓` | メタデータ項目を移動 |
| `Ctrl-p` / `Ctrl-n` | 上 / 下へ移動（Emacs キーバインド） |
| `Ctrl-a` / `Ctrl-e` | 検索欄の先頭 / 末尾へ移動 |
| `Ctrl-b` / `Ctrl-f` | 検索欄を左 / 右へ移動 |
| `Ctrl-d` / `Ctrl-k` / `Ctrl-u` | 検索欄で削除 / 行末まで削除 / 全消去 |
| `r` | 直前に決めた候補一覧を開き直す（1階層のみ・何度でも可） |
| `f` | 再生中の曲をお気に入りへ追加／解除 |
| `l` | お気に入り一覧を開き、選んだ曲を再生 |
| `c` | チャプタ一覧を開き、選んだ位置へジャンプ |
| `Enter` | 選んだ項目を起点に候補一覧を開き、1曲を次曲として予約 |
| `p` | 一時停止 / 再開 |
| `n` | 次曲へ進む（予約曲、なければタイトル検索の先頭） |
| `q` | 終了 |

`m` で選んだタイトル・作詞・作曲・歌手・ジャンルは、選択履歴として保存される。以後の候補は選択回数と再生回数（古い記録は徐々に減衰）を使って順位付けされる。直近100曲は候補から外れ、再生が終わると予約曲へ自動で進む。

予約がないまま曲が終わった場合は、終わった曲のタイトルで YouTube を検索し、直近100曲を除いた検索結果の先頭を自動再生する。

`mpv` の技術ログ（音声・字幕トラックの一覧など）は TUI を壊さないよう非表示にしている。曲名とメタデータ、再生操作はすべて TUI 内に表示される。

kitty 上では、YouTube のサムネイルを再生画面右側にジャケットとして表示する。ジャケットは画面幅のおよそ3分の1を使う。幅90列・高さ16行未満では、メタデータを優先して画像を隠す。

チャプタのある動画では、再生中のチャプタ名を曲名の下に表示する。選曲後に詳細メタデータを取得するため、検索結果の取得速度は変わらない。
