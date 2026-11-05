{#
  dbt-sqlite normally hashes snapshot keys with the optional SQLean md5
  extension. Keep snapshots portable across local Windows and Linux Airflow
  by encoding the same arguments with built-in SQLite functions instead.

  Length prefixes make the concatenation unambiguous even when a value
  contains the separator. As in dbt's default implementation, NULL and the
  empty string intentionally share the same representation.
#}
{% macro sqlite__snapshot_hash_arguments(args) -%}
    lower(hex(
        {%- for arg in args %}
        cast(length(coalesce(cast({{ arg }} as text), '')) as text)
        || ':' || coalesce(cast({{ arg }} as text), '')
        {%- if not loop.last %} || '|' || {% endif -%}
        {%- endfor %}
    ))
{%- endmacro %}

{#
  dbt-sqlite 1.10 closes changed versions but omits delete records from its
  update predicate. Include both change types so hard_deletes: invalidate has
  the same behavior as dbt's default snapshot merge implementation.
#}
{% macro sqlite__snapshot_merge_sql(target, source, insert_cols) -%}
    {%- set insert_cols_csv = insert_cols | join(', ') -%}
    {%- set columns = config.get("snapshot_table_column_names")
        or get_snapshot_table_column_names() -%}
    {%- set target_valid_to =
        (target ~ '.' ~ columns.dbt_valid_to) | trim -%}

    {% set update_sql %}
    update {{ target }}
    set {{ columns.dbt_valid_to }} = (
        select DBT_INTERNAL_SOURCE.{{ columns.dbt_valid_to }}
        from {{ source }} as DBT_INTERNAL_SOURCE
        where DBT_INTERNAL_SOURCE.{{ columns.dbt_scd_id }} =
                {{ target }}.{{ columns.dbt_scd_id }}
          and DBT_INTERNAL_SOURCE.dbt_change_type in ('update', 'delete')
    )
    where
        {% if config.get('dbt_valid_to_current') %}
        {%- set current_value = config.get('dbt_valid_to_current') | trim -%}
        ({{ equals(target_valid_to, current_value) }}
         or {{ target_valid_to }} is null);
        {% else %}
        {{ target_valid_to }} is null;
        {% endif %}
    {% endset %}

    {% do adapter.add_query(update_sql, auto_begin=False) %}

    insert into {{ target }} ({{ insert_cols_csv }})
    select
        {% for column in insert_cols -%}
        DBT_INTERNAL_SOURCE.{{ column }}{% if not loop.last %}, {% endif %}
        {%- endfor %}
    from {{ source }} as DBT_INTERNAL_SOURCE
    where DBT_INTERNAL_SOURCE.dbt_change_type = 'insert';
{%- endmacro %}
