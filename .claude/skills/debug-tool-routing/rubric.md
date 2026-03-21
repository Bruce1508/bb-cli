# debug-tool-routing Rubric

Use this rubric after diagnosing or fixing a routing problem.

## 1. Intent clarity

- Was the user request interpreted correctly?
- Was mixed intent recognized instead of forced into a single-tool answer?

## 2. Existing-tool fit

- Was the current tool surface checked before proposing a new tool?
- Was the most relevant tool identified accurately?
- Were docstrings reviewed as part of the interface?

## 3. Data-path correctness

- Was the underlying DB or content-tree path checked when needed?
- Was the problem distinguished from a pure prompt issue?
- Was a missing-data problem kept separate from a weak-tool-interface problem?

## 4. Fix quality

- Is the proposed fix at the smallest correct layer?
- Does it improve future routing quality without introducing unnecessary complexity?
- Does it preserve grounded behavior?

## 5. Honest limits

- If a needed capability is missing, was that stated clearly?
- If follow-up work is required, was it named explicitly rather than hidden?
