from .analysis import analyze_local_metadata
from .analysis import normalize_output
from .course_selection import (
    EVALUATION_POLICY_VERSION,
    SELECTION_POLICY_VERSION,
    candidate_is_auto_approve_eligible,
    course_title_similarity,
    evaluate_course_candidate,
    get_course_selection_policy,
    normalize_course_title,
)
