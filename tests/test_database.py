from app.db import database


def test_execution_round_trip_preserves_validation_trace_and_schema(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DATABASE_PATH', str(tmp_path / 'test.db'))
    database.initialize_database()
    record = {
        'execution_id': 'test-execution-1', 'prompt': 'Return company name.', 'model': 'qwen3:4b',
        'status': 'needs_review', 'original_response': '{"company_name":"BluePeak Systems"}',
        'final_response': '{"company_name":"BluePeak Systems"}',
        'initial_validation': {'quality_score': 50.0}, 'validation': {'quality_score': 50.0},
        'failure_type': 'possible_hallucination', 'recovery_strategy': 'regenerate_with_source_constraints',
        'retry_count': 2, 'fallback_model_used': True,
        'execution_trace': ['Initial validation failed', 'Recovery attempted'], 'total_latency_ms': 123.4,
        'source_content': 'BluePeak Systems has exactly 42 employees.',
        'expected_schema': {'type': 'object'}, 'fallback_model': 'llama3.2:3b',
    }
    database.save_execution(record)
    restored = database.get_execution('test-execution-1')
    assert restored is not None and restored['status'] == 'needs_review'
    assert restored['initial_validation'] == {'quality_score': 50.0}
    assert restored['validation'] == {'quality_score': 50.0}
    assert restored['execution_trace'] == ['Initial validation failed', 'Recovery attempted']
    assert restored['expected_schema'] == {'type': 'object'}
    assert restored['fallback_model_used'] is True
    assert restored['fallback_model'] == 'llama3.2:3b'


def test_failure_list_only_contains_needs_review(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DATABASE_PATH', str(tmp_path / 'test.db'))
    database.initialize_database()
    base = {'prompt': 'Test prompt', 'model': 'qwen3:4b', 'original_response': 'response', 'final_response': 'response', 'execution_trace': []}
    database.save_execution({**base, 'execution_id': 'ok', 'status': 'passed'})
    database.save_execution({**base, 'execution_id': 'bad', 'status': 'needs_review'})
    assert len(database.list_executions()) == 2
    assert [item['execution_id'] for item in database.list_failures()] == ['bad']


def test_benchmark_round_trip_and_history_omits_results_from_list(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DATABASE_PATH', str(tmp_path / 'test.db'))
    database.initialize_database()
    summaries = [{'model': 'qwen3:4b', 'validation_pass_rate_percent': 50.0}]
    results = [{'model': 'qwen3:4b', 'response': 'hello'}]
    database.save_benchmark('run-1', ['qwen3:4b', 'llama3.2:3b'], 1, summaries, results)
    saved = database.get_benchmark('run-1')
    assert saved['models'] == ['qwen3:4b', 'llama3.2:3b']
    assert saved['summaries'] == summaries and saved['results'] == results
    history = database.list_benchmarks()
    assert len(history) == 1 and 'results' not in history[0]
