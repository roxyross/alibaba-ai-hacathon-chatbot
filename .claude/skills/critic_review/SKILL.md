---
name: critic_review
description: Structured critical review of text, code, plans, or decisions. Evaluates logic, evidence, clarity, and completeness — surfaces weaknesses, suggests alternatives, and gives an overall verdict.
inputs:
  content: The text, code, plan, or decision description to review
  type: '"text" | "code" | "plan" | "decision" | "research"'
  depth: '"quick" | "standard" | "deep"'
  criteria: List of evaluation criteria to focus on (optional, defaults to logic/evidence/clarity/completeness)
---

# critic_review

Provides structured critical feedback on any piece of content. The skill analyzes the content against specified criteria, identifies strengths and weaknesses, and returns a structured critique with an overall verdict.

## Content types

- **text**: essays, emails, reports, proposals, blog posts, any written text
- **code**: source code (non-git review), pseudocode, architecture decisions
- **plan**: project plans, roadmaps, proposals, strategies
- **decision**: pros/cons lists, expected value analyses, framework decisions
- **research**: claims with sources, literature reviews, data-driven arguments

## Depth levels

- **quick**: Top 3 strengths and 3 key weaknesses, brief summary.
- **standard**: Full structured critique with sections (see below).
- **deep**: Standard + missing perspectives, second-order effects, benchmarking against alternatives.

## Output structure

```json
{
  "verdict": "strong | adequate | weak | flawed",
  "overall": "one-sentence assessment",
  "strengths": ["what works well and why"],
  "weaknesses": [
    {
      "name": "weakness name",
      "evidence": "specific quote or data point",
      "why_it_matters": "consequence",
      "suggested_fix": "how to address it (or null)"
    }
  ],
  "minor_issues": ["other issues, briefly"],
  "missing_perspectives": ["angles not addressed"],
  "summary": "2-3 sentence actionable takeaway",
  "depth": "quick | standard | deep",
  "criteria_evaluated": ["logic", "evidence", "clarity", "completeness"]
}
```

## How it works

1. Analyzes the content against the specified criteria (or defaults).
2. Applies a structured evaluation rubric appropriate to the content type.
3. Identifies fatal flaws vs. polish issues vs. missing perspectives.
4. Returns the structured critique above.

## Notes

- This skill uses the AI gateway to generate the critique — it is not a simple rule-based evaluation.
- The `critic_review` skill delegates to the Critic/Evaluator Agent internally when depth is "deep" or when the content type is "research" (requiring fact-checking).
