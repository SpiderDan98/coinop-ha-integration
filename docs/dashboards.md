# Dashboards

## Monthly costs on a dashboard

The cost sensors are running totals that work with long-term statistics, so a statistic card can show what printing cost this month (replace the entity with your Device's Total cost sensor):

```yaml
type: statistic
entity: sensor.my_printer_total_cost
name: Printing this month
period:
  calendar:
    period: month
stat_type: change
```

For a bar per month, use a statistics graph card:

```yaml
type: statistics-graph
entities:
  - sensor.my_printer_total_cost
period: month
stat_types:
  - change
chart_type: bar
days_to_show: 365
```

Corrections and deleted Runs change the totals at the moment you make them, so they show up in that month rather than rewriting earlier ones.
