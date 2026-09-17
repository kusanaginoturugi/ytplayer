from ytplayer import youtube


def test_browser_cookie_option(monkeypatch) -> None:
    monkeypatch.setenv("YTPLAYER_COOKIES_FROM_BROWSER", "firefox:music")
    assert youtube.options()["cookiesfrombrowser"] == ("firefox", "music")


def test_cookie_file_option(monkeypatch) -> None:
    monkeypatch.setenv("YTPLAYER_COOKIES", "/tmp/cookies.txt")
    assert youtube.options()["cookiefile"] == "/tmp/cookies.txt"


def test_youtube_video_id_gets_a_thumbnail_fallback() -> None:
    track = youtube._track({"id": "rNHPVU617_o", "title": "song"})
    assert track.thumbnail == "https://i.ytimg.com/vi/rNHPVU617_o/hqdefault.jpg"


def test_chapters_are_converted_to_track_metadata() -> None:
    track = youtube._track({"id": "rNHPVU617_o", "title": "mix", "chapters": [
        {"title": "First", "start_time": 0, "end_time": 120},
        {"title": "Second", "start_time": 120, "end_time": 240},
    ]})
    assert track.chapters[1].title == "Second"
    assert track.chapters[1].start_time == 120
