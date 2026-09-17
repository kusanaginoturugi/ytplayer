from ytplayer.app import App


def test_cell_wrapping_keeps_full_width_japanese_inside_limit() -> None:
    lines = App._wrap_cells("歌詞: あいうえお", 8)
    assert lines == ["歌詞: あ", "いうえお"]
    assert all(App._display_width(line) <= 8 for line in lines)
