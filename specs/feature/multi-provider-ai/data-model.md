# Data Model: Multi-Provider AI Abstraction

**Feature:** multi-provider-ai | **Date:** 2026-09-02

---

## Entity: Provider

Represents a configured AI provider.

| Field | Type | Validation | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `name` | `str` | One of: `deepseek`, `grok`, `openai`, `gemini` | |
| `enabled` | `bool` | Default `True` | Operator toggle; circuit breaker independent |
| `api_key_env_var` | `str` | Non-empty, must exist in env | Name of env var, not the key itself |
| `base_url` | `str` | Valid URL | Provider API endpoint |
| `timeout_seconds` | `float` | `> 0`, default `10.0` | Per-request timeout |
| `health_status` | `enum` | `healthy`, `degraded`, `unavailable` | Computed from circuit state + probe |
| `routing_priority` | `int` | `1–4`, unique | Lower = higher priority |
| `supports_streaming` | `bool` | Default `True` | For future provider-specific features |
| `created_at` | `datetime` | | |
| `updated_at` | `datetime` | | |

**State transitions:**
- `enabled=True` + circuit closed → `healthy`
- `enabled=True` + circuit half-open → `degraded`
- `enabled=False` OR circuit open → `unavailable`

---

## Entity: Model

Represents a specific model within a provider.

| Field | Type | Validation | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `provider_id` | `UUID` | FK → Provider | |
| `name` | `str` | e.g. `deepseek-chat-v3`, `grok-3` | Provider-native model name |
| `display_name` | `str` | e.g. `DeepSeek V3` | Shown in attribution UI |
| `task_types` | `list[str]` | e.g. `["general", "coding", "reasoning"]` | Routing hints |
| `cost_per_1k_input_tokens` | `float` | `>= 0` | USD |
| `cost_per_1k_output_tokens` | `float` | `>= 0` | USD |
| `max_tokens` | `int` | `> 0` | |
| `enabled` | `bool` | Default `True` | Per-model toggle |

---

## Entity: TokenUsageLog

Immutable audit log of token consumption.

| Field | Type | Validation | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `request_id` | `UUID` | Indexed | Links to conversation / request |
| `provider_id` | `UUID` | FK → Provider | |
| `model_id` | `UUID` | FK → Model | |
| `input_tokens` | `int` | `>= 0` | |
| `output_tokens` | `int` | `>= 0` | |
| `cost_usd` | `float` | `>= 0` | Computed at log time |
| `latency_ms` | `int` | `>= 0` | Wall-clock time |
| `provider_response_ms` | `int` | `>= 0` | Provider-reported latency (if available) |
| `timestamp` | `datetime` | | |

---

## Entity: ProviderPreference

User-level provider preference.

| Field | Type | Validation | Notes |
|---|---|---|---|
| `id` | `UUID` | PK | |
| `user_id` | `UUID` | FK → User, unique | One preference per user |
| `preferred_provider` | `str` | One of provider names, nullable | Null = auto |
| `updated_at` | `datetime` | | |

---

## API Request/Response Models (Pydantic v2)

### AIRequest
```python
class AIRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    messages: list[Message]                        # Chat format
    provider: str | None = None                    # Request-level override
    task_type: Literal["general", "coding", "reasoning"] = "general"
    temperature: float = Field(ge=0, le=2, default=0.7)
    max_tokens: int | None = Field(gt=0)
    stream: bool = False
    timeout_seconds: float | None = Field(gt=0, le=60)
```

### AIResponse
```python
class AIResponse(BaseModel):
    content: str
    provider: str
    model: str
    agent_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    request_id: UUID
```

### StreamingChunk
```python
class StreamingChunk(BaseModel):
    delta: str
    provider: str
    model: str
    done: bool = False
```

### ProviderHealthResponse
```python
class ProviderHealthResponse(BaseModel):
    providers: list[ProviderStatus]

class ProviderStatus(BaseModel):
    name: str
    status: Literal["healthy", "degraded", "unavailable"]
    circuit_state: Literal["closed", "half_open", "open"]
    last_error: str | None
    last_success: datetime | None
```

---

## Database Schema (Prisma)

```prisma
model Provider {
  id              String   @id @default(uuid())
  name            String   @unique
  enabled         Boolean  @default(true)
  apiKeyEnvVar    String
  baseUrl         String
  timeoutSeconds  Float    @default(10.0)
  routingPriority Int      @unique
  supportsStreaming Boolean @default(true)
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt
  models          Model[]
  tokenLogs       TokenUsageLog[]
}

model Model {
  id                   String   @id @default(uuid())
  providerId           String
  provider             Provider @relation(fields: [providerId], references: [id])
  name                 String
  displayName          String
  taskTypes            String[]  // JSON array stored as string
  costPer1kInputTokens Float
  costPer1kOutputTokens Float
  maxTokens            Int
  enabled              Boolean  @default(true)
  tokenLogs            TokenUsageLog[]
  @@unique([providerId, name])
}

model TokenUsageLog {
  id                  String   @id @default(uuid())
  requestId           String   @index
  providerId          String
  provider            Provider @relation(fields: [providerId], references: [id])
  modelId             String
  model               Model    @relation(fields: [modelId], references: [id])
  inputTokens         Int
  outputTokens        Int
  costUsd             Float
  latencyMs           Int
  providerResponseMs  Int?
  timestamp           DateTime @default(now())
}

model UserPreference {
  id                String  @id @default(uuid())
  userId            String  @unique
  preferredProvider String?
  updatedAt         DateTime @updatedAt
}
```
