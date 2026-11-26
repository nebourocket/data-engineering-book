{% macro clean_text(column_name) %}
    nullif(lower(trim({{ column_name }})), '')
{% endmacro %}
