"""Political aggregation rules (doc 00 0.12, doc 12 12.2)."""
from finbox.politics import (
    aggregate_allocation,
    aggregate_binary,
    aggregate_categorical,
    aggregate_scalar,
)


def test_scalar_mean_clamp_round():
    # doc 12 12.2.1: A=100bps, B=200bps -> 150
    assert aggregate_scalar([100, 200], [1, 1], lo=0, hi=4000, tick=1) == 150
    assert aggregate_scalar([100, 200, 300], [1, 1, 1], 0, 4000, 1) == 200
    # clamp to range
    assert aggregate_scalar([9000], [1], lo=0, hi=4000, tick=1) == 4000
    # round to tick (175 -> nearest 25 = 175; 188 -> 200)
    assert aggregate_scalar([188], [1], lo=0, hi=4000, tick=25) == 200
    # weights
    assert aggregate_scalar([100, 200], [3, 1], 0, 4000, 1) == 125


def test_binary_majority():
    # mean of {0.8,0.6,0.3,0.2} = 0.475 < 0.5 -> No (doc 12 12.2.2)
    assert aggregate_binary([8000, 6000, 3000, 2000], [1, 1, 1, 1]) is False
    assert aggregate_binary([8000, 6000, 5000], [1, 1, 1]) is True   # mean 0.633
    assert aggregate_binary([5000, 5000], [1, 1]) is True            # exactly 0.5 -> Yes


def test_categorical_argmax_min_index_tie():
    opts = ["AGRICULTURE", "MANUFACTURING", "ENERGY"]
    scores = [{"AGRICULTURE": 5, "MANUFACTURING": 7, "ENERGY": 4},
              {"AGRICULTURE": 7, "MANUFACTURING": 8, "ENERGY": 5}]
    # totals {12, 15, 9} -> MANUFACTURING (doc 12 12.2.3)
    assert aggregate_categorical(scores, [1, 1], opts) == "MANUFACTURING"
    # tie -> earliest option
    tie = [{"AGRICULTURE": 1, "MANUFACTURING": 1, "ENERGY": 0}]
    assert aggregate_categorical(tie, [1], opts) == "AGRICULTURE"


def test_allocation_normalize_mean_integerize():
    # doc 12 12.2.4: A=[2,1,1]->[.5,.25,.25], B=[0,1,3]->[0,.25,.75]; mean [.25,.25,.5]
    res = aggregate_allocation([[2, 1, 1], [0, 1, 3]], [1, 1], total=100)
    assert sum(res) == 100
    assert res == [25, 25, 50]
