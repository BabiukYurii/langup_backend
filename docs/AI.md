# AI layer

All model calls go through one wrapper (`services/ai/client.py`) so retries, timeouts,
structured-output parsing, model selection and token/cost accounting live in a single place.
Default model: latest Claude (e.g. `claude-opus-4-8`); provider is swappable via config.

## Tasks (`enums/ai.py: AITaskType`)

| Task                  | Service                        | Input → Output |
|-----------------------|--------------------------------|----------------|
| CONTEXT_ANALYSIS      | `context_analysis.py`          | word + sentence + page context → resolved sense, register, examples |
| DIFFICULTY_ESTIMATION | `difficulty_estimation.py`     | word + user history → difficulty score |
| EXERCISE_GENERATION   | `exercise_generation.py`       | word + context + type → exercise payload + answer |
| EXPLANATION           | `explanation.py`               | word / wrong answer → explanation, hint |
| QUIZ_GENERATION       | `quiz_generation.py`           | user's weak items → dynamic quiz |
| LEARNING_PATH         | `learning/learning_path.py`    | goals + weaknesses → ordered milestones |

Prompts live in `services/ai/prompts.py`. Responses are validated into Pydantic schemas
(`schemas/ai.py`); invalid output raises `AIResponseValidationError` (and is retried).

## Execution model

- **Sync (request path):** small, latency-sensitive calls (on-demand explanation).
- **Async (Celery + events):** capture-time context analysis, batch exercise generation,
  quiz/path generation. Each run is persisted to `ai_generations` (inputs, outputs, model,
  tokens, status) for cost tracking, debugging and caching.
- **Resilience:** `tenacity` retries with backoff; `httpx` timeouts; prompt caching where
  supported to cut cost; graceful fallback to template-based generators if AI is unavailable.

## Personalization loop

Attempts → `WeaknessAnalysisService` (aggregate errors) → AI difficulty + recommendations →
`LearningPathService` (re)builds the path → `SpacedRepetitionService` schedules reviews.
The result is adaptive difficulty, targeted exercises, and a personalized learning path.
