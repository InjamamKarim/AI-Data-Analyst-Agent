from eval.metrics import rows_equal, safe_sql_rate, valid_efficiency_score


def test_execution_match_rounds_floats_and_ignores_order():
    assert rows_equal([{"revenue": 1.004}], [{"revenue": 1.0}])
    assert rows_equal([{"region": "South"}, {"region": "North"}], [{"region": "North"}, {"region": "South"}])
    assert not rows_equal([{"region": "South"}, {"region": "North"}], [{"region": "North"}, {"region": "South"}], ordered=True)
    assert not rows_equal([{"revenue": 1}], [{"revenue": 2}])


def test_ves_rewards_correct_fast_queries_only():
    assert valid_efficiency_score(False, 1, 1) == 0
    assert valid_efficiency_score(True, 1, 1) == 1
    assert valid_efficiency_score(True, 1, 4) == 0.5
    assert valid_efficiency_score(True, 4, 1) == 1


def test_safe_sql_rate():
    assert safe_sql_rate([True, True, True]) == 1
    assert safe_sql_rate([True, False]) == 0.5
    assert safe_sql_rate([]) == 1
