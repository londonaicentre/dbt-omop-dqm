{% test dqm_plausibility_low_value(model, column_name, min_value, threshold=0, threshold_type='static_percentage') %}

            /*
            Tests if any values in a column are below a specified minimum value.

            Args:
                model: Model being tested
                column_name: Column to check values in
                min_value: Minimum allowed value (when using dates, specify it in quotes like min_value: "'2020-01-01'")
                threshold: Maximum allowed value for violations (default: 0)
                threshold_type: Type of threshold to apply (options: static_number, static_percentage; default: static_percentage)

            Note:
            - This test only sets the threshold, the logic for testing against the threshold is done in the python script.
                - The fail_calc returns:
                    - For static_percentage: percentage of violated rows
                    - For static_number: number of violated rows
            */

        {{
            config(
                tags=['dqm'],
                severity='warn',
                meta={
                    'category': 'plausibility',
                    'threshold_type': threshold_type,
                    'threshold': threshold
                },
                description='Validates that values are not below a specified minimum',
                fail_calc="case when '" ~ threshold_type ~ "' = 'static_number' then num_violated_rows else pct_violated_rows end"
            )
        }}

            with violation_stats as (
                select
                    sum(case
                        when {{ column_name }} < {{ min_value }} then 1
                        else 0
                    end) as num_violated_rows,
                    count(*) as total_rows
                from {{ model }}
                where {{ column_name }} is not null
            )
            select
                num_violated_rows,
                round(
                    (num_violated_rows::float / nullif(total_rows, 0)::float * 100),
                    0
                )::int as pct_violated_rows
            from violation_stats

{% endtest %}