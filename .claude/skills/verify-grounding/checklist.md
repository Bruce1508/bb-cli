# verify-grounding Checklist

Use this checklist when reviewing an AI-facing Blackboard answer.

## Claim tracing

- Can each Blackboard-facing fact be traced to a tool result, local DB value, or cached file?
- Are there any statements that only sound plausible but are not directly supported?
- If a statement is inferred, is that visible in the wording?

## Certainty control

- Does the answer claim too much from too little data?
- Does it imply current Blackboard state that the repo cannot actually verify?
- Does it hide uncertainty instead of naming it?

## Empty and partial states

- If the DB is empty, does the response say so clearly?
- If the cache is missing, does the response say what to do next?
- If the tool surface only partially supports the question, does the response stay honest about that limit?

## Product fit

- Does the response remain practical for a student using a terminal-first workflow?
- Does the answer help the user move forward instead of ending at “not supported”?
- Does the answer preserve the product promise of grounded help?

## Follow-up clarity

- If a tool or capability gap exists, is it identified explicitly?
- Is the suggested follow-up small, realistic, and aligned with the active sprint?
