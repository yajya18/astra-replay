A person recorded a first-person video of a task and is asking about it:
"{{ query }}"

These are the most relevant moments found in the video (times in m:ss):
{% for hit in hits %}- Step {{ hit.order }} "{{ hit.title }}" from {{ hit.start_label }} to {{ hit.end_label }}: {{ hit.snippet }}
{% endfor %}
Answer in ONE sentence, in second person, citing the time as m:ss and the step title, e.g.
"You added salt at 2:14, during 'Season the eggs'." If none of the moments answers the question,
say so in one sentence. Also return the time in seconds you cited (or null).
Return ONLY JSON: {"answer": "...", "time": 134.0}

<data>
{{ data }}
</data>
