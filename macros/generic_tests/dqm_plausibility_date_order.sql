{% test dqm_plausibility_date_order(model, start_date_column, end_date_column, threshold=0, threshold_type='static_percentage') %}

            /*
            Tests if the end date in a record is on or after the start date.
            NEEDS TESTING!!!

            Args:
                model: Model being tested
                start_date_column: Column containing the start date/timestamp
                end_date_column: Column containing the end date/timestamp
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
                description='Validates that an end date is not before a start date',
                fail_calc="case when '" ~ threshold_type ~ "' = 'static_number' then num_violated_rows else pct_violated_rows end"
            )
        }}

            with violation_stats as (
                select
                    sum(case
                        when {{ end_date_column }} < {{ start_date_column }} then 1
                        else 0
                    end) as violated_rows,
                    count(*) as total_rows
                from {{ model }}
                where {{ start_date_column }} is not null
                  and {{ end_date_column }} is not null
            )
            select
                violated_rows as num_violated_rows,
                round(
                    (violated_rows::float / nullif(total_rows, 0)::float * 100),
                    0
                )::int as pct_violated_rows
            from violation_stats

{% endtest %}