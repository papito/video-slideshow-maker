import pytest

from slideshow.join import Boundary, crossfade_plan, filter_graph


def test_offsets_accumulate_minus_fades():
    boundaries, total = crossfade_plan([4.0, 4.0, 10.0], 0.5)
    assert boundaries == [Boundary(offset=3.5, fade=0.5), Boundary(offset=7.0, fade=0.5)]
    assert total == pytest.approx(17.0)


def test_fade_is_clamped_to_half_the_shorter_neighbour():
    boundaries, total = crossfade_plan([4.0, 0.6, 4.0], 0.5)
    assert boundaries[0].fade == pytest.approx(0.3)
    assert boundaries[1].fade == pytest.approx(0.3)
    assert boundaries[1].offset == pytest.approx(4.0 + 0.6 - 0.3 - 0.3)
    assert total == pytest.approx(8.0)


def test_single_and_empty():
    assert crossfade_plan([5.0], 0.5) == ([], 5.0)
    assert crossfade_plan([], 0.5) == ([], 0.0)


def test_filter_graph_chains_inputs():
    boundaries, _ = crossfade_plan([4.0, 4.0, 4.0], 0.5)
    graph = filter_graph([4.0, 4.0, 4.0], boundaries)
    assert graph.count("xfade=") == 2
    assert graph.count("acrossfade=") == 2
    assert "[0:v][1:v]xfade=transition=fade:duration=0.5000:offset=3.5000[v1]" in graph
    assert "[v1][2:v]xfade=" in graph
    assert graph.endswith("[v2]null[vout];[ax2]anull[aout]")


def test_zero_fade_uses_concat():
    graph = filter_graph([4.0, 4.0], [Boundary(offset=4.0, fade=0.0)])
    assert "concat=n=2:v=1:a=0" in graph
    assert "xfade" not in graph
