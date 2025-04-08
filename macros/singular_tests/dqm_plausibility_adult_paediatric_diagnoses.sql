{% test dqm_plausibility_adult_paediatric_diagnoses(model,threshold = 0) %}

        /*
            NEEDS TESTING!
            Tests if the percentage of paediatric diagnoses in condition_occurrence that are assigned to adult patients
            exceeds a specified threshold.

            Args:
                threshold: Maximum allowed value for violations (default: 0)

            Note:
                - The fail_calc returns the actual percentage, so the warning message "Got n results" shows the violation percentage.
        */

        {{
            config(
                tags=['dqm'],
                severity='warn',
                meta={
                    'category': 'plausibility',
                    'threshold_type': 'static_number',
                    'threshold': threshold
                },
                description='Returns percentage of paediatric diagnoses that are assigned to adult patients',
                fail_calc='num_violated_rows'
            )
        }}

        with paediatric_conditions as (
            select
                co.master_person_id,
                co.condition_start_datetime,
                co.condition_source_value
            from {{ model }} co
            inner join {{ ref('base_internal__paediatric_diagnosis_codes') }} pc
                on co.condition_source_value = pc.code
        ),

        diagnosis_checks as (
            select
                case
                    when p.birth_datetime is null then null
                    when date_diff('year',pc.condition_start_datetime, p.birth_datetime) > 18 then 1
                    else 0
                end as is_violation
            from paediatric_conditions pc
            inner join {{ ref('ext_person') }} p
                on pc.master_person_id = p.master_person_id
        )

        select
            sum(case when is_violation is not null then is_violation else 0 end) as num_violated_rows
        from diagnosis_checks

{% endtest %}