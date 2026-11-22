You are writing the recap of a first-person video in which a person performs a hands-on task.
Below is the ordered list of action steps that were detected, with timestamps (seconds).

For every step, write a short, human title in imperative form with a consistent style,
e.g. "Chop the onion", "Whisk the eggs", "Tighten the left hinge screw". Keep each title under
8 words. Do not merge, drop, invent or reorder steps: return exactly {{ n_steps }} titles in the same order.

Group the steps into 2 to 6 phases (for example "Prep", "Cook", "Plate"). Each phase covers a
contiguous range of steps given by 1-based "start_order" and "end_order"; together the phases must
cover every step exactly once, in order.{% if n_steps < 2 %} With a single step, use one phase.{% endif %}

Also write:
- "task_name": one line naming the whole task, e.g. "Making a tomato omelette".
- "summary": 2 to 3 sentences summarising what the person did, in second person ("You ...").
{% if reference %}
The person intended to follow this procedure (use it for naming only if it matches):
{% for step in reference %}{{ loop.index }}. {{ step }}
{% endfor %}{% endif %}
Return ONLY JSON of the form:
{"task_name": "...", "summary": "...", "titles": ["...", "..."],
 "phases": [{"name": "Prep", "start_order": 1, "end_order": 3}, ...]}

<data>
{{ data }}
</data>
