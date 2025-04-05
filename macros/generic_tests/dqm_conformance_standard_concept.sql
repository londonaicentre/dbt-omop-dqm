{% test dqm_conformance_standard_concept(model, column_name, threshold=0, threshold_type='static_percentage') %}

            /*
            Tests if concept IDs are valid standard concepts in the OMOP vocabulary.
            Adapted from OHDSI DataQualityDashboard field_is_standard_valid_concept test.
            NEEDS TESTING!

            Args:
                model: Model being tested
                column_name: Column containing the concept_id to validate
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
                    'category': 'conformance',
                    'threshold_type': threshold_type,
                    'threshold': threshold
                },
                description='Validates that concept IDs are valid standard concepts in the OMOP vocabulary',
                fail_calc="case when '" ~ threshold_type ~ "' = 'static_number' then num_violated_rows else pct_violated_rows end"
            )
        }}

            with violation_stats as (
                select
                    sum(case
                        when m.{{ column_name }} is not null
                            and c.concept_id != 0
                            and (c.standard_concept != 'S' or c.invalid_reason is not null)
                        then 1
                        else 0
                    end) as violated_rows,
                    count(*) as total_rows
                from {{ model }} m
                left join {{ ref('concept') }} c
                    on m.{{ column_name }} = c.concept_id
                where m.{{ column_name }} is not null
            )
            select
                violated_rows as num_violated_rows,
                round(
                    (violated_rows::float / nullif(total_rows, 0)::float * 100),
                    0
                )::int as pct_violated_rows
            from violation_stats

{% endtest %}