{% test dqm_plausibility_events_after_death(model,threshold = 0) %}

        /*
            NEEDS TESTING!
            Tests if the percentage of clinical events that occur after a patient's death date
            exceeds a specified threshold. This includes conditions, procedures, drug exposures,
            measurements, and observations.

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
                    'threshold_type': 'static_percentage',
                    'threshold': threshold
                },
                description='Returns percentage of clinical events that occur after a death date',
                fail_calc='pct_violated_rows'
            )
        }}

        with death_dates as (
            select
                master_person_id,
                death_date
            from {{ model }}
            where death_date is not null
        ),

        -- Process each event type separately
        condition_stats as (
            select
                count(*) as total_events,
                count(case when e.condition_start_date > d.death_date then 1 end) as violation_count
            from {{ ref('ext_condition_occurrence') }} e
            inner join death_dates d using (master_person_id)
        ),

        procedure_stats as (
            select
                count(*) as total_events,
                count(case when e.procedure_date > d.death_date then 1 end) as violation_count
            from {{ ref('ext_procedure_occurrence') }} e
            inner join death_dates d using (master_person_id)
        ),

        drug_stats as (
            select
                count(*) as total_events,
                count(case when e.drug_exposure_start_date > d.death_date then 1 end) as violation_count
            from {{ ref('ext_drug_exposure') }} e
            inner join death_dates d using (master_person_id)
        ),

        measurement_stats as (
            select
                count(*) as total_events,
                count(case when e.measurement_date > d.death_date then 1 end) as violation_count
            from {{ ref('ext_measurement') }} e
            inner join death_dates d using (master_person_id)
        ),

        observation_stats as (
            select
                count(*) as total_events,
                count(case when e.observation_date > d.death_date then 1 end) as violation_count
            from {{ ref('ext_observation') }} e
            inner join death_dates d using (master_person_id)
        ),

        all_violations as (
            select
                sum(violation_count)::float as total_violations,
                sum(total_events)::float as total_events
            from (
                select total_events, violation_count from condition_stats
                union all
                select total_events, violation_count from procedure_stats
                union all
                select total_events, violation_count from drug_stats
                union all
                select total_events, violation_count from measurement_stats
                union all
                select total_events, violation_count from observation_stats
            )
        )

        select
            round(
                (total_violations / nullif(total_events, 0)) * 100,
                0
            )::int as pct_violated_rows
        from all_violations

{% endtest %}