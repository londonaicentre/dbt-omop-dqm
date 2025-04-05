import pytest
from datetime import datetime
from dqm_dashboard.transform_run_results import (
    calculate_static_threshold,
    calculate_moving_average_status,
    TestResult,
    update_threshold_status,
    RowCountResult,
    # Import status constants
    STATUS_TEST_PASSED,
    STATUS_EXCEEDED_THRESHOLD,
    STATUS_INSUFFICIENT_RUNS,
    STATUS_ABOVE_THRESHOLD,
    STATUS_BELOW_THRESHOLD,
    STATUS_WITHIN_THRESHOLD,
)


def test_update_threshold_status_pass():
    """Test that pass status sets threshold_status to 'Test Passed'."""
    test_result = TestResult(
        invocation_id="test-123",
        test_name="test_name",
        clean_test_name="test_name",
        status="pass",
        execution_time=1.5,
        generated_at=datetime.now(),
        threshold=10,
    )

    update_threshold_status(test_result)

    assert test_result.threshold_status == STATUS_TEST_PASSED  # Use constant


def test_static_threshold_exceeded():
    """Test when violations exceed the threshold."""
    result = calculate_static_threshold(violations=15000, threshold=10000)
    assert result == STATUS_EXCEEDED_THRESHOLD  # Use constant


def test_static_threshold_within_range():
    """Test when violations are within threshold."""
    result = calculate_static_threshold(violations=5, threshold=15)
    assert (
        result == STATUS_TEST_PASSED
    )  # Use constant (Function returns 'Test Passed' when <= threshold)


def test_static_threshold_equal():
    """Test when violations equal threshold."""
    result = calculate_static_threshold(violations=10, threshold=10)
    assert (
        result == STATUS_TEST_PASSED
    )  # Use constant (Function returns 'Test Passed' when <= threshold)


def test_moving_average_insufficient_data():
    """Test when there's not enough historical runs."""
    result = calculate_moving_average_status(
        historical_counts=[100, 200, 300],  # Only 3 runs
        current_count=400,
        threshold=10,
    )
    assert result.threshold_status == STATUS_INSUFFICIENT_RUNS
    assert result.upper_bound == 0
    assert result.lower_bound == 0


def test_moving_average_above_threshold():
    """Test when current count is above the threshold."""
    # Average = (100 + 100 + 100 + 100 + 120) / 5 = 104
    result = calculate_moving_average_status(
        historical_counts=[100, 100, 100, 100],
        current_count=120,  # Higher than average
        threshold=10,  # 10% threshold
    )
    assert result.threshold_status == STATUS_ABOVE_THRESHOLD
    assert result.upper_bound == 114  # 104 * (1 + 10/100)
    assert result.lower_bound == 93  # 104 * (1 - 10/100)


def test_moving_average_below_threshold():
    """Test when current count is below the threshold."""
    # Average = (100 + 100 + 100 + 100 + 80) / 5 = 96
    result = calculate_moving_average_status(
        historical_counts=[100, 100, 100, 100],
        current_count=80,  # Lower than average
        threshold=10,  # 10% threshold
    )
    assert result.threshold_status == STATUS_BELOW_THRESHOLD
    assert result.upper_bound == 105  # 96 * (1 + 10/100)
    assert result.lower_bound == 86  # 96 * (1 - 10/100)


def test_moving_average_within_threshold():
    """Test when current count is within the threshold."""
    # Average = (100 + 100 + 100 + 100 + 105) / 5 = 101
    result = calculate_moving_average_status(
        historical_counts=[100, 100, 100, 100],
        current_count=105,
        threshold=10,  # 10% threshold
    )
    assert (
        result.threshold_status == STATUS_WITHIN_THRESHOLD
    )  # Use constant (Function returns 'Test Passed' when within bounds)
    assert result.upper_bound == 111  # 101 * (1 + 10/100)
    assert result.lower_bound == 90  # 101 * (1 - 10/100)
