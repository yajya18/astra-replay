You are analysing a first-person (egocentric) video of a person doing a hands-on task
such as cooking, assembly, repair or a lab procedure. You see {{ n_frames }} frames sampled
in time order from one short window of the video ({{ "%.1f"|format(start) }}s to {{ "%.1f"|format(end) }}s).
Frame times (seconds): {{ frame_times }}.
{% if grid %}The frames are arranged left-to-right, top-to-bottom in one grid image; each tile is labelled with its time.
{% endif %}
Describe the single main ACTION the person's hands are performing in this window, as
verb + object + tool. Focus on what the hands do, not on the scene.
{% if previous_action %}
The previous window showed: "{{ previous_action }}". Keep the same wording if the action continues.
{% endif %}{% if vocabulary %}
The person may be following these reference steps. Prefer their wording when it fits,
but describe what you actually see:
{% for step in vocabulary %}- {{ step }}
{% endfor %}{% endif %}{% if transcript %}
Speech heard during this window (a hint only; trust the frames): "{{ transcript }}"
{% endif %}
Rules:
- "verb": one lowercase base-form verb, e.g. "chop", "pour", "screw", "whisk". Use "unknown" if unclear.
- "object": the main thing acted on, short noun phrase, e.g. "onion".
- "tool": the tool or utensil in use, or "" if hands only.
- "hands": one of "left", "right", "both", "none".
- "is_idle": true only if no meaningful hand action happens (waiting, looking around).
- "description": one plain sentence describing the action.
- "confidence": 0.0 to 1.0, how sure you are.

Answer with ONLY a JSON object with exactly these keys:
{"is_idle": false, "verb": "chop", "object": "onion", "tool": "knife", "hands": "both",
 "description": "Chopping an onion on a wooden board with a chef's knife.", "confidence": 0.82}
