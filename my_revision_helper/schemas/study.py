"""
Request and response models for the study programme API.

Field names are camelCase to match the existing endpoints and the frontend.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------


class ChildSubjectPayload(BaseModel):
    subject: str
    baselineScore: Optional[float] = None
    yearAverage: Optional[float] = None
    targetScore: Optional[float] = None
    weeklyMinutes: int = 0
    priority: int = 0
    focusTopics: List[str] = Field(default_factory=list)
    reportNotes: Optional[str] = None


class ChildSubjectResponse(ChildSubjectPayload):
    id: str
    gap: Optional[float] = None  # baseline minus year average; negative = behind


class ChildCreateRequest(BaseModel):
    name: str
    yearGroup: Optional[str] = None
    school: Optional[str] = None
    colour: str = "orange"
    avatarEmoji: Optional[str] = None


class ChildUpdateRequest(BaseModel):
    name: Optional[str] = None
    yearGroup: Optional[str] = None
    school: Optional[str] = None
    colour: Optional[str] = None
    avatarEmoji: Optional[str] = None
    isActive: Optional[bool] = None


class ChildResponse(BaseModel):
    id: str
    name: str
    yearGroup: Optional[str] = None
    school: Optional[str] = None
    colour: str = "orange"
    avatarEmoji: Optional[str] = None
    isActive: bool = True
    createdAt: str


class ChildListResponse(BaseModel):
    items: List[ChildResponse]


# ---------------------------------------------------------------------------
# Study plans
# ---------------------------------------------------------------------------


class PlanBlockPayload(BaseModel):
    dayOfWeek: int  # 0 = Monday
    blockIndex: int
    subject: str
    focus: Optional[str] = None
    plannedMinutes: int = 50
    weekCycle: Optional[str] = None  # 'A', 'B', or null for every week


class PlanBlockResponse(PlanBlockPayload):
    id: str


class StudyPlanResponse(BaseModel):
    id: str
    childId: str
    title: str
    summary: Optional[str] = None
    startDate: Optional[str] = None
    endDate: Optional[str] = None
    weeklyMinutesTarget: int = 0
    daysPerWeek: int = 5
    isActive: bool = True
    blocks: List[PlanBlockResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Papers
# ---------------------------------------------------------------------------


class ResourceLink(BaseModel):
    """
    An instructional link, e.g. the video to watch before attempting a paper.

    `kind` distinguishes what the student is being asked to do with it, so the
    label can be rendered sensibly: watch, read, practise.
    """

    url: str
    label: Optional[str] = None
    kind: str = "watch"


class PaperQuestionResponse(BaseModel):
    """
    A question as shown to a student.

    Deliberately has no expected_answer field: the answer key is never part of
    a student-facing payload.
    """

    id: str
    number: str
    orderIndex: int
    questionText: str
    sessionLabel: Optional[str] = None
    band: Optional[str] = None
    topic: Optional[str] = None
    marks: int = 1


class PaperListItem(BaseModel):
    id: str
    title: str
    subject: str
    paperType: str
    topics: List[str] = Field(default_factory=list)
    weekLabel: Optional[str] = None
    questionCount: int = 0
    totalMarks: Optional[int] = None
    estimatedMinutes: Optional[int] = None
    hasAnswerKey: bool = False
    # Whether the uploaded document itself may be given to a student. False when
    # an answer key was found inside it, which is the usual case for a workbook.
    originalIsStudentSafe: bool = False
    resources: List[ResourceLink] = Field(default_factory=list)
    parseStatus: str = "pending"
    createdAt: str


class PaperListResponse(BaseModel):
    items: List[PaperListItem]
    total: int


class PaperDetailResponse(PaperListItem):
    questions: List[PaperQuestionResponse] = Field(default_factory=list)
    questionText: Optional[str] = None  # Student-safe document text
    sourceFileId: Optional[str] = None
    parseError: Optional[str] = None


class BulkUploadItem(BaseModel):
    """
    The outcome for one file in a bulk upload.

    Reported per filename so a parent can see which of ten documents failed and
    retry just that one, rather than being told the whole batch went wrong.
    """

    filename: str
    status: str  # ok, failed
    paper: Optional[PaperListItem] = None
    error: Optional[str] = None


class BulkUploadResponse(BaseModel):
    items: List[BulkUploadItem]
    succeeded: int
    failed: int


class PaperUpdateRequest(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    paperType: Optional[str] = None
    weekLabel: Optional[str] = None
    topics: Optional[List[str]] = None
    estimatedMinutes: Optional[int] = None
    resources: Optional[List[ResourceLink]] = None


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


class AssignmentCreateRequest(BaseModel):
    childId: str
    title: str
    subject: str
    assignmentType: str = "paper"  # paper, task
    paperId: Optional[str] = None
    instructions: Optional[str] = None
    resourceUrl: Optional[str] = None
    resources: Optional[List[ResourceLink]] = None
    estimatedMinutes: Optional[int] = None
    dueDate: Optional[str] = None  # ISO date
    # The day this is planned for. Distinct from the deadline: a plan may set work
    # for Monday that is not due until Friday.
    scheduledDate: Optional[str] = None  # ISO date
    weekLabel: Optional[str] = None
    verification: str = "upload"  # upload, self_report, timer, none
    sortOrder: int = 0


class AssignmentBulkCreateRequest(BaseModel):
    """Assign one paper to several children at once."""

    childIds: List[str]
    assignments: List[AssignmentCreateRequest]


class AssignmentUpdateRequest(BaseModel):
    title: Optional[str] = None
    instructions: Optional[str] = None
    resourceUrl: Optional[str] = None
    resources: Optional[List[ResourceLink]] = None
    estimatedMinutes: Optional[int] = None
    dueDate: Optional[str] = None
    scheduledDate: Optional[str] = None
    weekLabel: Optional[str] = None
    status: Optional[str] = None
    verification: Optional[str] = None
    sortOrder: Optional[int] = None


class AssignmentMarkingSummary(BaseModel):
    id: str
    percentage: Optional[float] = None
    marksAwarded: Optional[float] = None
    marksAvailable: Optional[float] = None
    weakTopics: List[str] = Field(default_factory=list)
    markedAt: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: str
    childId: str
    title: str
    subject: str
    assignmentType: str
    paperId: Optional[str] = None
    instructions: Optional[str] = None
    resourceUrl: Optional[str] = None
    # The paper's own links followed by this assignment's extras, already merged
    # so the client does not have to know the precedence rule.
    resources: List[ResourceLink] = Field(default_factory=list)
    estimatedMinutes: Optional[int] = None
    dueDate: Optional[str] = None
    scheduledDate: Optional[str] = None
    # The day it will actually be done and the day it is late after, resolved
    # server-side so every view agrees on the fallback rule.
    plannedOn: Optional[str] = None
    dueOn: Optional[str] = None
    isOverdue: bool = False
    weekLabel: Optional[str] = None
    verification: str = "upload"
    status: str = "todo"
    sortOrder: int = 0
    createdAt: str
    completedAt: Optional[str] = None
    questionCount: int = 0
    latestMarking: Optional[AssignmentMarkingSummary] = None


class AssignmentListResponse(BaseModel):
    items: List[AssignmentResponse]
    total: int


class TodayBlock(BaseModel):
    """One slot in today's timetable."""

    blockIndex: int
    subject: str
    focus: Optional[str] = None
    plannedMinutes: int = 50


class TodayResponse(BaseModel):
    """
    Today's work, split so the day has a visible end.

    `dueToday` is the list to work through; `overdue` is what slipped; and
    `upcoming` is a short look ahead rather than the whole backlog.
    """

    date: str
    dayOfWeek: int  # 0 = Monday
    blocks: List[TodayBlock] = Field(default_factory=list)
    plannedMinutes: int = 0
    dueToday: List[AssignmentResponse] = Field(default_factory=list)
    overdue: List[AssignmentResponse] = Field(default_factory=list)
    upcoming: List[AssignmentResponse] = Field(default_factory=list)


class SelfReportRequest(BaseModel):
    """A child confirming they did a non-markable task."""

    minutesSpent: Optional[int] = None
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# Submissions and marking
# ---------------------------------------------------------------------------


class QuestionMarkResponse(BaseModel):
    id: str
    orderIndex: int
    questionNumber: Optional[str] = None
    questionText: Optional[str] = None
    studentAnswer: Optional[str] = None
    expectedAnswer: Optional[str] = None
    marksAwarded: float = 0
    marksAvailable: float = 1
    verdict: Optional[str] = None
    feedback: Optional[str] = None
    topic: Optional[str] = None


class MarkingResponse(BaseModel):
    id: str
    submissionId: str
    childId: str
    assignmentId: Optional[str] = None
    paperId: Optional[str] = None
    subject: str
    marksAwarded: Optional[float] = None
    marksAvailable: Optional[float] = None
    percentage: Optional[float] = None
    overallFeedback: Optional[str] = None
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    weakTopics: List[str] = Field(default_factory=list)
    markedBy: str = "ai"
    markedAt: Optional[str] = None
    questionMarks: List[QuestionMarkResponse] = Field(default_factory=list)


class MarkingListItem(BaseModel):
    id: str
    assignmentId: Optional[str] = None
    assignmentTitle: Optional[str] = None
    subject: str
    percentage: Optional[float] = None
    marksAwarded: Optional[float] = None
    marksAvailable: Optional[float] = None
    weakTopics: List[str] = Field(default_factory=list)
    markedAt: Optional[str] = None


class MarkingListResponse(BaseModel):
    items: List[MarkingListItem]
    total: int


class QuestionMarkOverrideRequest(BaseModel):
    """Parent correcting the AI's mark on a single question."""

    marksAwarded: float
    verdict: Optional[str] = None
    feedback: Optional[str] = None


# ---------------------------------------------------------------------------
# Progress and dashboards
# ---------------------------------------------------------------------------


class TopicMasteryResponse(BaseModel):
    subject: str
    topic: str
    attempts: int = 0
    masteryPct: Optional[float] = None
    status: str = "weak"
    lastAssessedAt: Optional[str] = None


class SubjectProgressResponse(BaseModel):
    subject: str
    baselineScore: Optional[float] = None
    yearAverage: Optional[float] = None
    targetScore: Optional[float] = None
    latestScore: Optional[float] = None
    gapToAverage: Optional[float] = None  # latest minus year average
    baselineGap: Optional[float] = None  # baseline minus year average
    weeklyMinutes: int = 0
    assignmentsTotal: int = 0
    assignmentsDone: int = 0
    minutesLogged: int = 0
    weakTopics: List[str] = Field(default_factory=list)


class ScoreLogItem(BaseModel):
    id: str
    subject: str
    label: str
    scorePct: Optional[float] = None
    yearAveragePct: Optional[float] = None
    gap: Optional[float] = None
    source: str = "manual"
    recordedAt: str


class ChildProgressResponse(BaseModel):
    """Everything the dashboard and landing page need in one request."""

    child: ChildResponse
    plan: Optional[StudyPlanResponse] = None
    subjects: List[SubjectProgressResponse] = Field(default_factory=list)
    scoreLog: List[ScoreLogItem] = Field(default_factory=list)
    weakTopics: List[TopicMasteryResponse] = Field(default_factory=list)
    upNext: List[AssignmentResponse] = Field(default_factory=list)
    recentMarkings: List[MarkingListItem] = Field(default_factory=list)
    assignmentsTotal: int = 0
    assignmentsDone: int = 0
    assignmentsDueThisWeek: int = 0
    assignmentsOverdue: int = 0
    minutesLoggedThisWeek: int = 0
    weeklyMinutesTarget: int = 0
    averagePercentage: Optional[float] = None
    streakDays: int = 0


class RetestRequest(BaseModel):
    """Build a practice test from what a marking showed was weak."""

    markingId: Optional[str] = None
    subject: Optional[str] = None
    topics: List[str] = Field(default_factory=list)
    questionCount: int = 8
    questionStyle: str = "free-text"


class RetestResponse(BaseModel):
    revisionId: str
    runId: Optional[str] = None
    subject: str
    topics: List[str] = Field(default_factory=list)
    questionCount: int
