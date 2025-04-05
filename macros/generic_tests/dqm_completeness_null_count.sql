{% test dqm_completeness_null_count(model, column_name, threshold=0, threshold_type='static_percentage') %}

            /*
            Tests if the number/percentage of null values in a column exceeds a specified threshold.

            Args:
                model: Model being tested
                column_name: Column to check for null values
                threshold: Maximum allowed value for violations (default: 0)
                threshold_type: Type of threshold to apply (options: static_number, static_percentage; default: static_percentage)

            Note:
            - This test only sets the threshold, the logic for testing against the threshold is done in the python script.
                - The fail_calc returns:
                    - For static_percentage: percentage of null values
                    - For static_number: number of null values
            */

        {{
            config(
                tags=['dqm'],
                severity='warn',
                meta={
                    'category': 'completeness',
                    'threshold_type': threshold_type,
                    'threshold': threshold
                },
                description='Validates the completeness of a column by checking null values',
                fail_calc="case when '" ~ threshold_type ~ "' = 'static_number' then num_violated_rows else pct_violated_rows end"
            )
        }}

            with violation_stats as (
                select
                    sum(case
                        when {{ column_name }} is null then 1
                        else 0
                    end) as null_rows,
                    count(*) as total_rows
                from {{ model }}
            )
            select
                null_rows as num_violated_rows,
                round(
                    (null_rows::float / nullif(total_rows, 0)::float * 100),
                    0
                )::int as pct_violated_rows
            from violation_stats

{% endtest %}