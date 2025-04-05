import pytest
from dqm_dashboard.parse_dbt_artifacts import (
    process_manifest_data,
    process_run_results,
    Manifest,
    RunResult,
)


def test_process_empty_manifest_data():
    """Test processing of empty manifest data"""
    empty_manifest = {"nodes": {}}
    meta_dict = process_manifest_data(empty_manifest)
    assert meta_dict == {}


def test_process_empty_run_results():
    """Test processing of empty run results data"""
    empty_run_data = {"metadata": {}, "results": []}
    results = process_run_results(empty_run_data, {})
    assert results == []


def test_process_manifest_data():
    """Test processing of manifest data with a simple test case"""
    test_manifest = {
        "nodes": {
            "test.project_name.dqm_completeness_test": {
                "meta": {
                    "category": "completeness",
                    "threshold_type": "static_number",
                    "threshold": 10,
                }
            }
        }
    }

    result = process_manifest_data(test_manifest)

    # Check if data was processed correctly
    assert "test.project_name.dqm_completeness_test" in result
    assert result["test.project_name.dqm_completeness_test"].category == "completeness"
    assert result["test.project_name.dqm_completeness_test"].threshold == 10
    assert (
        result["test.project_name.dqm_completeness_test"].threshold_type
        == "static_number"
    )


def test_process_run_results():
    """Test processing of run results with basic test data"""
    test_run_data = {
        "metadata": {
            "invocation_id": "test-123",
            "generated_at": "2025-03-11T17:18:24.798916Z",
        },
        "results": [
            {
                "unique_id": "test.project_name.dqm_completeness_test",
                "status": "warn",
                "execution_time": 20.563233,
                "message": "Got 40 results, configured to warn if != 0",
                "failures": 40,
                "compiled_code": "select count(*) as failures from model where value is null",
            }
        ],
    }

    test_meta = {
        "test.project_name.dqm_completeness_test": Manifest(
            category="completeness", threshold_type="static_number", threshold=10
        )
    }

    expected_result = RunResult(
        invocation_id="test-123",
        unique_id="test.project_name.dqm_completeness_test",
        status="warn",
        execution_time=20.563233,
        message="Got 40 results, configured to warn if != 0",
        compiled_code="select count(*) as failures from model where value is null",
        relation_name=None,
        violations=40,
        node_name="dqm_completeness_test",
        resource_type="test",
        category="completeness",
        threshold_type="static_number",
        threshold=10,
        generated_at="2025-03-11T17:18:24.798916Z",
    )

    results = process_run_results(test_run_data, test_meta)
    assert len(results) == 1
    assert results[0] == expected_result


def test_process_run_results_missing_fields():
    """Test processing run results with missing required fields"""
    incomplete_run_data = {
        "metadata": {},
        "results": [
            {
                "unique_id": "test.project_name.test1",
                "status": "pass",
                "execution_time": 1.0,
            }
        ],
    }

    results = process_run_results(incomplete_run_data, {})
    assert len(results) == 1

    expected_result = RunResult(
        invocation_id=None,
        unique_id="test.project_name.test1",
        status="pass",
        execution_time=1.0,
        message=None,
        compiled_code=None,
        relation_name=None,
        violations=0,
        node_name="test1",
        resource_type="test",
        category=None,
        threshold_type=None,
        threshold=None,
        generated_at=None,
    )

    assert results[0] == expected_result


def test_process_manifest_data_invalid_thresholds():
    """Test processing manifest data with invalid threshold values"""
    test_manifest = {
        "nodes": {
            # Test negative threshold
            "test.project_name.test1": {
                "meta": {"threshold_type": "static_number", "threshold": -10}
            },
            # Test percentage threshold > 100
            "test.project_name.test2": {
                "meta": {"threshold_type": "static_percentage", "threshold": 150}
            },
        }
    }
    result = process_manifest_data(test_manifest)

    assert result["test.project_name.test1"].threshold == 0
    assert result["test.project_name.test2"].threshold == 0


def test_process_manifest_data_valid_thresholds():
    """Test processing manifest data with valid threshold values"""
    test_manifest = {
        "nodes": {
            # Test valid static_number
            "test.project_name.test1": {
                "meta": {"threshold_type": "static_number", "threshold": 10}
            },
            "test.project_name.test2": {
                "meta": {"threshold_type": "static_percentage", "threshold": 65}
            },
        }
    }
    result = process_manifest_data(test_manifest)

    assert result["test.project_name.test1"].threshold == 10
    assert result["test.project_name.test2"].threshold == 65
