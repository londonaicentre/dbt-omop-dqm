{% test dqm_plausibility_gender_specific_diagnoses(model,threshold = 0) %}

        /*
            NEEDS TESTING!
            Tests if the percentage of gender-specific diagnoses in condition_occurrence that don't match
            the patient's gender exceeds a specified threshold.

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
                description='Returns percentage of gender-specific diagnoses that do not match patient gender',
                fail_calc='num_violated_rows'
            )
        }}

        with gender_specific_conditions as (
            select
                co.master_person_id,
                co.condition_source_value,
                case
                    when m.code is not null then 'Male'
                    when f.code is not null then 'Female'
                end as expected_gender
            from {{ model }} co
            left join {{ ref('base_internal__male_diagnosis_codes') }} m
                on co.condition_source_value = m.code
            left join {{ ref('base_internal__female_diagnosis_codes') }} f
                on co.condition_source_value = f.code
            where m.code is not null or f.code is not null
        ),

        gender_checks as (
            select
                case
                    when p.gender_concept_name is null then null
                    when gsc.expected_gender = 'Male' and p.gender_concept_name = 'Female' then 1
                    when gsc.expected_gender = 'Female' and p.gender_concept_name = 'Male' then 1
                    else 0
                end as is_violation
            from gender_specific_conditions gsc
            inner join {{ ref('ext_person') }} p
                on gsc.master_person_id = p.master_person_id
        )

        select
            sum(case when is_violation is not null then is_violation else 0 end) as num_violated_rows
        from gender_checks

{% endtest %}