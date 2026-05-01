"""Pydantic models for API request/response."""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class IngestRequest(BaseModel):
    project_id: str = Field(..., description="Project slug")
    incremental: bool = Field(True, description="If true, only new/changed files")
    name: str | None = Field(None, description="Project name (used when creating)")
    sources: list[str] | None = Field(None, description="Paths to index (used when creating)")


class IngestResponse(BaseModel):
    project_id: str
    status: str = "started"
    message: str


class UserContextIn(BaseModel):
    """Optional request-time user data for personalization (e.g. from zapzap/sistemaBA)."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(None, description="Display name")
    birth_date: str | None = Field(
        None,
        description="Birth date (DD/MM/YYYY or ISO)",
        validation_alias=AliasChoices("birth_date", "birthDate"),
    )
    cep: str | None = None
    city: str | None = None
    state: str | None = None
    health: str | None = Field(None, description="Health notes (allergies, limitations, etc.)")
    interesse: str | None = Field(None, description="Onboarding interest slug (e.g. aprender_a_pedalar)")
    registered: bool | None = Field(None, description="Whether the user is already registered in the system")


class ChatTurn(BaseModel):
    """One turn for optional client-provided history on POST /ask (zapzap)."""

    model_config = ConfigDict(populate_by_name=True)

    role: str = Field(..., description="'user' or 'assistant'")
    text: str = Field(
        ...,
        description="Message text",
        validation_alias=AliasChoices("text", "content"),
    )


class AskRequest(BaseModel):
    project_id: str = Field(..., description="Project slug")
    question: str = Field(..., min_length=1)
    user_id: str | None = Field(None, description="End-user identifier (e.g. WhatsApp phone) for conversation context")
    user_context: UserContextIn | None = Field(
        None,
        description="Optional snapshot (name, birth_date, cep, city, state, health, interesse, registered)",
    )
    history: list[ChatTurn] | None = Field(
        None,
        description="Recent WhatsApp turns; used for this reply instead of DB-only history when sent",
    )
    system_prompt: str | None = Field(
        None,
        description="Client system prompt (e.g. Bike Anjo persona); prepended to server RAG instructions",
        validation_alias=AliasChoices("system_prompt", "systemPrompt"),
    )
    model: str | None = Field(None, description="Model alias ('fast' or 'smart') or specific model name")
    hint: str | None = Field(None, description="Optional hint for auto-router")

    model_config = ConfigDict(populate_by_name=True)


class AskResponse(BaseModel):
    job_id: str
    message: str
    status_url: str
    result_url: str


class AudioJobResponse(BaseModel):
    """202 response for POST /audio/transcribe and POST /audio/ask."""

    job_id: str
    message: str
    status_url: str
    result_url: str


class StatusResponse(BaseModel):
    job_id: str
    status: str  # queued | working | done | no_answer | need_more_info | failed | cancelled
    client_status: str = Field(
        ...,
        description="Zapzap-style status: 'processing' while queued or working; otherwise same as status",
    )
    progress: str | None = None
    created_at: str | None = None


class SourceRef(BaseModel):
    """Internal ref (path/snippet); used by dashboard. Not exposed to end-user API."""
    id: str
    path: str
    snippet: str


class UserSourceRef(BaseModel):
    """External reference for end user: only URL when present in library. No file paths."""
    url: str


class ResultResponse(BaseModel):
    job_id: str
    status: str
    answer: str | None = None
    sources: list[UserSourceRef] = []
    confidence: str | None = None
    transcript: str | None = Field(
        None,
        description="Filled when job_kind is audio_transcribe or audio_ask after STT",
    )
    stt_metadata: dict | None = Field(
        None,
        description="STT metadata: language, duration_seconds, transcribe_seconds, model, segment_count",
    )


# --- User Profile ---


class UserProfileRequest(BaseModel):
    user_id: str = Field(..., description="End-user identifier (e.g. WhatsApp phone)")
    project_id: str = Field(..., description="Project slug")
    display_name: str | None = Field(None, description="User's display name")
    birth_date: str | None = Field(None, description="Birth date (YYYY-MM-DD)")
    notes: str | None = Field(None, description="Free-text notes about the user")
    metadata: dict | None = Field(None, description="Arbitrary project-specific fields (health, preferences, etc.)")


class UserProfileResponse(BaseModel):
    user_id: str
    project_id: str
    display_name: str | None = None
    birth_date: str | None = None
    notes: str | None = None
    metadata: dict = {}
    created_at: str | None = None
    updated_at: str | None = None


# --- Conversation Management ---


class ConversationResetRequest(BaseModel):
    user_id: str = Field(..., description="End-user identifier")
    project_id: str = Field(..., description="Project slug")


class ConversationResetResponse(BaseModel):
    user_id: str
    project_id: str
    messages_deleted: int
    message: str


class MaintenanceResponse(BaseModel):
    users_processed: int
    summaries_created: int
    messages_deleted: int


# --- Extract (zapzap onboarding: sync extraction from free-text) ---


class ExtractRequest(BaseModel):
    """Request for synchronous extraction (e.g. zapzap onboarding)."""
    task: str = Field("extract", description="Must be 'extract'")
    step: str = Field(
        ...,
        description="Step id: interesse, nome, cpf, email, nascimento, cep, or payment_nf_confirmation (JSON object string)",
    )
    question: str = Field(..., description="Question that was asked to the user")
    user_reply: str = Field(..., description="User's free-text reply", alias="userReply")
    model: str | None = Field(None, description="Model alias ('fast' or 'smart') or specific model name")

    model_config = {"populate_by_name": True}


class ExtractResponse(BaseModel):
    """Extracted value or null if not extractable."""
    extracted: str | None = None


class ExtractMultiFieldSpec(BaseModel):
    """Field descriptor for POST /extract-multi."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="Step id: nome, cpf, email, nascimento, cep, interesse")
    label: str = Field(..., description="Human label for the LLM")
    example: str = Field("", description="Example value")


class ExtractMultiContext(BaseModel):
    """Optional context for extract-multi (onboarding or payment NF confirmation).

    Extra keys (e.g. current_nf, instruction, step) are kept for zapzap payment flow.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    current_step: str | None = Field(None, validation_alias=AliasChoices("current_step", "currentStep"))
    already_collected: dict[str, str] = Field(default_factory=dict)


class ExtractMultiRequest(BaseModel):
    """Multi-field extraction from one user message (zapzap smart onboarding)."""

    model_config = ConfigDict(populate_by_name=True)

    task: str = Field("extract_multi", description="Discriminator; use extract_multi")
    user_reply: str = Field(..., alias="userReply", description="Free-text user message")
    fields: list[ExtractMultiFieldSpec] = Field(..., min_length=1)
    context: ExtractMultiContext | None = None
    model: str | None = Field(None, description="Model alias ('fast' or 'smart') or specific model name")


class ExtractMultiResponse(BaseModel):
    """Only keys successfully extracted; empty object if nothing parsed."""

    extracted: dict[str, str] = Field(default_factory=dict)


# --- Project CRUD ---


class ProjectCreateRequest(BaseModel):
    project_id: str = Field(..., description="Unique slug (e.g. 'bikeanjoall_2026')")
    name: str | None = Field(None, description="Human-readable name")
    sources: list[str] = Field(default_factory=list, description="Paths to index (folders)")
    config_json: dict | None = Field(None, description="Chunking, embedding_model, policies")
    themes: list[str] = Field(default_factory=list, description="Tags for auto-router")


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    sources: list[str] | None = None
    config_json: dict | None = None
    themes: list[str] | None = None


class ProjectResponse(BaseModel):
    project_id: str
    name: str | None = None
    sources: list[str] = []
    config_json: dict | None = None
    themes: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None
    index_stats: dict | None = Field(None, description="Chunks count and last_ingest (documents, chunks, at) when available")


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int


# --- Job Listing ---


class JobResponse(BaseModel):
    job_id: str
    project_id: str
    question: str
    status: str
    progress: str | None = None
    answer: str | None = None
    sources: list[UserSourceRef] = []
    confidence: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    job_kind: str | None = Field(None, description="ask | audio_transcribe | audio_ask")
    transcript: str | None = None


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int
    limit: int
    offset: int


class JobStatsResponse(BaseModel):
    total: int = 0
    by_status: dict[str, int] = {}
    by_project: dict[str, int] = {}
    last_24h: int = 0
    avg_duration_seconds: float | None = None


# --- NF Extract ---


class NFExtractResponse(BaseModel):
    status: str = "ok"
    source_type: str | None = None
    document_type: str = "unknown"
    file_name: str | None = None

    supplier_name: str | None = None
    supplier_code: str | None = None
    nf_number: str | None = None
    issue_date: str | None = None

    amount: float | None = None
    amount_type: str = "unknown"
    amount_deposit: float | None = None
    amount_tax: float | None = None

    description: str | None = None
    payment_pix_code: str | None = Field(default=None, alias="payment_pixCode")
    payment_bank: str | None = None
    payment_bank_agency: str | None = None
    payment_bank_account: str | None = None
    payment_bank_account_type: str = "unknown"
    payment_receiver_name: str | None = None
    payment_receiver_document: str | None = None

    service_recipient_code: str | None = Field(
        default=None,
        description="Tomador / service recipient tax id (digits only), when extractable.",
    )
    payment_type: str | None = Field(
        default=None,
        description="pix | boleto | transferencia | cartao_credito | dinheiro when inferable.",
    )

    confidence: float = 0.0
    confidence_by_field: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    raw_text_excerpt: str | None = None

    model_config = {"populate_by_name": True}

# --- Educational API ---

class VocabularyItem(BaseModel):
    id: str
    language: str = "zh-CN"
    hanzi: str
    pinyin: str
    translation: str
    level: str
    category: str | None = None
    example_sentence: str | None = None
    example_pinyin: str | None = None
    example_translation: str | None = None

class VocabularyCreateRequest(BaseModel):
    language: str = "zh-CN"
    hanzi: str
    pinyin: str
    translation: str
    level: str
    category: str | None = None
    example_sentence: str | None = None
    example_pinyin: str | None = None
    example_translation: str | None = None

class VocabularyListResponse(BaseModel):
    items: list[VocabularyItem]
    total: int

class GrammarExample(BaseModel):
    hanzi: str
    pinyin: str | None = None
    translation: str

class GrammarPoint(BaseModel):
    id: str
    language: str = "zh-CN"
    pattern: str
    explanation: str
    level: str
    examples: list[GrammarExample] = []

class GrammarCreateRequest(BaseModel):
    language: str = "zh-CN"
    pattern: str
    explanation: str
    level: str
    examples: list[GrammarExample] = []

class GrammarListResponse(BaseModel):
    items: list[GrammarPoint]
    total: int

class EduChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str | None = None
    language: str = Field("zh-CN", description="Target language")
    level: str | None = Field(None, description="HSK1..HSK6 or custom")
    history: list[ChatTurn] | None = None
    model: str | None = Field(
        None,
        description="Alias: fast | compact | smart | reasoner (DeepSeek R1), or explicit Ollama tag",
    )


class EduTranslationBlock(BaseModel):
    """Per-segment translations for Chinese Learning UI (pt / en / es)."""

    pt: str = ""
    en: str = ""
    es: str = ""


class EduChatSegment(BaseModel):
    """One logical phrase or sentence in the tutor reply."""

    hanzi: str
    pinyin: str = ""
    translation: EduTranslationBlock


class EduChatResponse(BaseModel):
    """reply ≈ full_reply_text (hanzi). reply_structured is always filled when HTTP 200: model output or server fallback."""

    reply: str
    language: str = "zh-CN"
    reply_structured: list[EduChatSegment] | None = None
    full_reply_text: str | None = Field(
        None,
        description="Hanzi-only full line when structured; same idea as concatenated segments",
    )

class ExerciseItem(BaseModel):
    type: str  # fill_blank | translation | char_recognition | sentence_construction
    prompt: str
    answer: str
    options: list[str] | None = None
    hint: str | None = None
    vocab_id: str | None = None

class ExerciseRequest(BaseModel):
    user_id: str | None = None
    language: str = "zh-CN"
    level: str = Field(..., description="HSK1..HSK6 or custom level")
    vocab_ids: list[str] | None = Field(None, description="Specific vocab IDs to use")
    exercise_types: list[str] | None = Field(None, description="fill_blank, translation, char_recognition, sentence_construction")
    count: int = Field(5, ge=1, le=20)
    model: str | None = None

class ExerciseResponse(BaseModel):
    language: str
    level: str
    exercises: list[ExerciseItem]
    count: int

class ProgressRecordRequest(BaseModel):
    user_id: str
    vocab_id: str
    correct: bool

class ProgressRecordResponse(BaseModel):
    user_id: str
    vocab_id: str
    seen_count: int
    correct_count: int
    mastered: bool


class NabilLocationCandidate(BaseModel):
    """One inferred location candidate for POST /nabilvideomap/qualify-caption."""

    model_config = ConfigDict(extra="ignore")

    label: str = ""
    kind: str = ""
    confidence: float | None = None


class NabilQualifyCaptionRequest(BaseModel):
    """nabilVideoMap batch: Instagram caption → structured row fields."""

    model_config = ConfigDict(populate_by_name=True)

    project_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1, description="Caption body only (UTF-8)")
    use_rag: bool = Field(False, description="Inject project index snippets when true")
    model: str | None = Field(
        None,
        description="Alias: fast | compact | smart | reasoner, or explicit Ollama model tag",
    )


class NabilQualifyCaptionResponse(BaseModel):
    """Fixed response shape; consumer maps to SQLite."""

    location_accuracy: str
    location_granularity: str
    location_primary_label: str
    llm_location_candidates: list[NabilLocationCandidate]
    location_ambiguity_notes: str
    location_confidence: float | None
    theme_primary: str
    theme_secondary: str
    theme_tags: str
    llm_theme_notes: str
    summary_140: str
