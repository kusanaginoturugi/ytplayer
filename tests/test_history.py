from pathlib import Path

from ytplayer.history import History
from ytplayer.models import Track
from ytplayer.downloader import existing_audio
from ytplayer.app import App
from ytplayer import app
from ytplayer.player import Player


def track(video_id: str, artist: str = "Ada") -> Track:
    return Track(video_id, f"Song {video_id}", f"https://example.test/{video_id}", artist=artist, genre="jazz")


def test_selected_facet_outweighs_unselected_track(tmp_path: Path) -> None:
    history = History(tmp_path / "history.sqlite3")
    history.record_play(track("one"), ("歌手", "Ada"))
    assert history.score(track("new", "Ada")) > history.score(track("other", "Bert"))
    history.close()


def test_recent_track_is_penalized(tmp_path: Path) -> None:
    history = History(tmp_path / "history.sqlite3")
    current = track("one")
    history.record_play(current)
    assert history.score(current) < history.score(track("two"))
    history.close()


def test_recent_video_ids_are_limited_to_requested_rotation(tmp_path: Path) -> None:
    history = History(tmp_path / "history.sqlite3")
    history.record_play(track("old"))
    history.record_play(track("new"))
    assert history.recent_video_ids(1) == {"new"}
    assert history.recent_video_ids(100) == {"old", "new"}
    history.close()


def test_favorite_can_be_added_listed_and_removed(tmp_path: Path) -> None:
    history = History(tmp_path / "history.sqlite3")
    favorite = track("favorite")
    assert history.toggle_favorite(favorite) is True
    assert history.is_favorite("favorite") is True
    assert history.favorites() == [favorite]
    assert history.toggle_favorite(favorite) is False
    assert history.favorites() == []
    history.close()


def test_existing_audio_is_matched_by_video_id(tmp_path: Path) -> None:
    path = tmp_path / "A title [favorite].m4a"
    path.touch()
    assert existing_audio(track("favorite"), tmp_path) == path


def test_second_candidate_is_used_for_the_provisional_queue(monkeypatch) -> None:
    candidates = [track("one"), track("two"), track("three")]
    monkeypatch.setattr(app, "search", lambda query: candidates)
    assert App.second_candidate(track("current"), {"one"}) == candidates[2]


def test_second_candidate_falls_back_to_the_first_available(monkeypatch) -> None:
    candidates = [track("one"), track("two")]
    monkeypatch.setattr(app, "search", lambda query: candidates)
    assert App.second_candidate(track("current"), {"one"}) == candidates[1]


def test_enqueue_reports_whether_mpv_accepted_the_playlist_item(monkeypatch) -> None:
    player = Player()
    monkeypatch.setattr(player, "_command", lambda command: {})
    assert player.enqueue(track("next")) is True
    monkeypatch.setattr(player, "_command", lambda command: None)
    assert player.enqueue(track("next")) is False
