{% test dqm_row_count_anomalies(model, threshold=10) %}

            /*
            Tests row count anomalies by monitoring volume changes over time.
            The actual anomaly detection logic (e.g., moving average comparison)
            is expected to be performed downstream by processing scripts based on
            the results and meta configuration of this test.

            Args:
                model: Model being tested
                threshold: Configuration value used by downstream processing (e.g., allowed deviation percentage). Default: 10

            Note:
            - This test returns the total row count of the model, aliased as 'violations'.
            - Downstream scripts use this count and the 'threshold' from meta config for anomaly checks.
            */

        {{
            config(
                tags=['dqm'],
                severity='warn',
                meta={
                    'category': 'anomaly_detection',
                    'threshold_type': 'moving_average',
                    'threshold': threshold
                },
                description='Returns total row count for downstream anomaly detection',
                fail_calc="violations"
            )
        }}

            select count(*) as violations
            from {{ model }}

{% endtest %}